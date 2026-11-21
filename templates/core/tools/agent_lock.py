#!/usr/bin/env python3
"""
core/tools/agent_lock.py - Agent concurrency lease, locking, and journal manager.

Provides high-speed atomic OS-level file locking, lease acquisition with TTL,
human priority preemption (vscode-user), lease release, write-off with SHA-256
integrity hashing, and audit journaling for multi-agent workflows.

Standard library only: zero external dependencies.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

HUMAN_PRIORITY_AGENTS = {"vscode-user"}


def iso_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_repo_root(custom_root: Optional[str] = None) -> str:
    """Locate the repository root directory."""
    if custom_root:
        return os.path.abspath(custom_root)
    env_root = os.environ.get("AGENT_LOCK_ROOT")
    if env_root:
        return os.path.abspath(env_root)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (
            (parent / "project.godot").is_file()
            or (parent / "game.py").is_file()
            or (parent / ".agent-state").is_dir()
        ):
            return str(parent)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(script_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(parent) == "tools" and os.path.basename(grandparent) == "core":
        return os.path.dirname(grandparent)
    if os.path.exists(os.path.join(parent, ".agent-state")) or os.path.exists(
        os.path.join(parent, "tools")
    ):
        return parent
    return os.path.abspath(os.getcwd())


def normalize_path(path_str: str, root_dir: str) -> str:
    """Normalize path to relative path with POSIX forward slashes from root_dir."""
    path_str = str(path_str).strip()
    if path_str.startswith("res://"):
        path_str = path_str[len("res://"):]
    clean = path_str.replace("\\", "/")
    if os.path.isabs(path_str):
        try:
            return os.path.relpath(path_str, root_dir).replace("\\", "/")
        except ValueError:
            return clean

    abs_from_cwd = os.path.abspath(path_str)
    try:
        rel_from_root = os.path.relpath(abs_from_cwd, root_dir).replace("\\", "/")
        if (
            rel_from_root.startswith("../")
            and not path_str.startswith("../")
            and not path_str.startswith("..\\")
        ):
            return os.path.normpath(clean).replace("\\", "/")
        return rel_from_root
    except ValueError:
        return os.path.normpath(clean).replace("\\", "/")


@contextmanager
def file_lock(lock_path: str, timeout: float = 10.0, retry_interval: float = 0.02):
    """Atomic OS-level file lock context manager using msvcrt (Windows) or fcntl (POSIX)."""
    lock_dir = os.path.dirname(os.path.abspath(lock_path))
    os.makedirs(lock_dir, exist_ok=True)
    f = open(lock_path, "a+b")
    f.seek(0, os.SEEK_END)
    if f.tell() == 0:
        f.write(b"\0")
        f.flush()

    start = time.time()
    locked = False
    while True:
        try:
            f.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            break
        except (OSError, IOError):
            if (time.time() - start) >= timeout:
                break
            time.sleep(retry_interval)

    if not locked:
        f.close()
        raise TimeoutError(
            f"Could not acquire lock on {lock_path} within {timeout:.1f}s"
        )

    try:
        yield
    finally:
        try:
            f.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


def get_state_dir(root_dir: str) -> str:
    state_dir = os.path.join(root_dir, ".agent-state")
    os.makedirs(state_dir, exist_ok=True)
    return state_dir


def load_leases_raw(state_dir: str) -> Dict[str, Any]:
    leases_file = os.path.join(state_dir, "leases.json")
    if not os.path.exists(leases_file):
        return {}
    try:
        with open(leases_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_leases(state_dir: str, leases: Dict[str, Any]) -> None:
    leases_file = os.path.join(state_dir, "leases.json")
    temp_file = os.path.join(state_dir, "leases.json.tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(leases, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(temp_file, leases_file)


def prune_expired_leases(leases: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    now = time.time()
    valid = {}
    pruned = 0
    for p, entry in leases.items():
        norm_key = str(p).replace("\\", "/")
        if isinstance(entry, dict) and float(entry.get("expires_at", 0)) > now:
            valid[norm_key] = entry
        else:
            pruned += 1
    return valid, pruned


def append_journal(state_dir: str, entry: Dict[str, Any]) -> None:
    journal_file = os.path.join(state_dir, "journal.jsonl")
    with open(journal_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def read_journal_recent(state_dir: str, limit: int = 10) -> List[Dict[str, Any]]:
    journal_file = os.path.join(state_dir, "journal.jsonl")
    if not os.path.exists(journal_file):
        return []
    entries = []
    try:
        with open(journal_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
                if len(entries) >= limit:
                    break
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    entries.reverse()
    return entries


def compute_file_hash(root_dir: str, rel_path: str) -> str:
    full_path = (
        rel_path
        if os.path.isabs(rel_path)
        else os.path.normpath(os.path.join(root_dir, rel_path))
    )
    if not os.path.isfile(full_path):
        return "DELETED"
    hasher = hashlib.sha256()
    try:
        with open(full_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return "ERROR"


def cmd_acquire(args, root_dir: str, state_dir: str, lock_path: str) -> int:
    is_human_priority = args.agent in HUMAN_PRIORITY_AGENTS or bool(getattr(args, "force", False))
    with file_lock(lock_path):
        raw_leases = load_leases_raw(state_dir)
        leases, pruned = prune_expired_leases(raw_leases)
        norm_paths = [normalize_path(p, root_dir) for p in args.paths]

        now = time.time()
        conflicts = []
        preempted = []
        for p in norm_paths:
            if p in leases:
                cur = leases[p]
                cur_owner = cur.get("agent_id", "unknown")
                if cur_owner != args.agent and cur.get("expires_at", 0) > now:
                    if is_human_priority:
                        preempted.append({
                            "file": p,
                            "previous_owner": cur_owner,
                            "previous_task_id": cur.get("task_id", ""),
                        })
                    else:
                        rem = round(cur.get("expires_at", 0) - now, 2)
                        conflicts.append({
                            "expires_at": cur.get("expires_at", 0),
                            "file": p,
                            "human_priority": cur_owner in HUMAN_PRIORITY_AGENTS,
                            "owner": cur_owner,
                            "remaining_ttl": rem,
                            "task_id": cur.get("task_id", ""),
                        })

        if conflicts:
            if pruned > 0:
                save_leases(state_dir, leases)
            if args.json:
                print(
                    json.dumps(
                        {
                            "action": "acquire",
                            "agent_id": args.agent,
                            "conflicts": conflicts,
                            "status": "conflict",
                            "task_id": args.task,
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(
                    f"[CONFLICT] Cannot acquire leases. {len(conflicts)} path(s) locked by another agent:"
                )
                for c in conflicts:
                    print(
                        f"  - {c['file']}: held by agent '{c['owner']}' (task: '{c['task_id']}', remaining TTL: {c['remaining_ttl']}s)"
                    )
            return 1

        expires_at = now + args.ttl
        for p in norm_paths:
            leases[p] = {
                "acquired_at": now,
                "agent_id": args.agent,
                "expires_at": expires_at,
                "priority": "human" if args.agent in HUMAN_PRIORITY_AGENTS else "normal",
                "task_id": args.task,
                "ttl": args.ttl,
            }

        save_leases(state_dir, leases)

        summary = (
            args.summary
            if args.summary
            else f"Acquired lease on {len(norm_paths)} file(s)"
            + (f" (preempted {len(preempted)} lease(s))" if preempted else "")
        )
        journal_entry = {
            "action": "acquire",
            "agent_id": args.agent,
            "file_hashes": {},
            "files": norm_paths,
            "preempted": preempted,
            "summary": summary,
            "task_id": args.task,
            "timestamp": iso_now(),
        }
        append_journal(state_dir, journal_entry)

    if args.json:
        print(
            json.dumps(
                {
                    "acquired": norm_paths,
                    "action": "acquire",
                    "agent_id": args.agent,
                    "expires_at": expires_at,
                    "preempted": preempted,
                    "status": "success",
                    "task_id": args.task,
                    "ttl": args.ttl,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"[OK] Acquired {len(norm_paths)} lease(s) for agent '{args.agent}':")
        for p in norm_paths:
            print(f"  - {p} (expires in {args.ttl}s)")
    return 0


def cmd_release(args, root_dir: str, state_dir: str, lock_path: str) -> int:
    is_human_priority = args.agent in HUMAN_PRIORITY_AGENTS or bool(getattr(args, "force", False))
    with file_lock(lock_path):
        raw_leases = load_leases_raw(state_dir)
        leases, pruned = prune_expired_leases(raw_leases)

        if args.paths:
            targets = [normalize_path(p, root_dir) for p in args.paths]
        else:
            if is_human_priority and not args.agent:
                targets = list(leases.keys())
            elif args.force:
                targets = list(leases.keys())
            elif args.agent:
                targets = [
                    p for p, l in leases.items() if l.get("agent_id") == args.agent
                ]
            else:
                targets = []

        released = []
        skipped = []
        for p in targets:
            if p in leases:
                cur = leases[p]
                if is_human_priority or cur.get("agent_id") == args.agent:
                    del leases[p]
                    released.append(p)
                else:
                    skipped.append({
                        "file": p,
                        "owner": cur.get("agent_id", "unknown"),
                        "reason": "Owned by different agent (use --force or --agent vscode-user to override)",
                    })

        if released or pruned > 0:
            save_leases(state_dir, leases)

        if released:
            summary = f"Released {len(released)} lease(s)" + (
                " (forced)" if args.force else ""
            )
            journal_entry = {
                "action": "release",
                "agent_id": args.agent or "unknown",
                "file_hashes": {},
                "files": released,
                "summary": summary,
                "task_id": args.task or "",
                "timestamp": iso_now(),
            }
            append_journal(state_dir, journal_entry)

    if args.json:
        print(
            json.dumps(
                {
                    "action": "release",
                    "agent_id": args.agent,
                    "released": released,
                    "skipped": skipped,
                    "status": "success",
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"[OK] Released {len(released)} lease(s).")
        for p in released:
            print(f"  - {p}")
        if skipped:
            print(f"[WARN] Skipped {len(skipped)} path(s) owned by other agents.")
    return 0


def cmd_write_off(args, root_dir: str, state_dir: str, lock_path: str) -> int:
    norm_paths = [normalize_path(p, root_dir) for p in args.paths]
    file_hashes = {p: compute_file_hash(root_dir, p) for p in norm_paths}

    with file_lock(lock_path):
        raw_leases = load_leases_raw(state_dir)
        leases, pruned = prune_expired_leases(raw_leases)

        released = []
        for p in norm_paths:
            if p in leases:
                del leases[p]
                released.append(p)

        save_leases(state_dir, leases)

        journal_entry = {
            "action": "write-off",
            "agent_id": args.agent,
            "file_hashes": file_hashes,
            "files": norm_paths,
            "summary": args.summary,
            "task_id": args.task or "",
            "timestamp": iso_now(),
        }
        append_journal(state_dir, journal_entry)

    if args.json:
        print(
            json.dumps(
                {
                    "action": "write-off",
                    "agent_id": args.agent,
                    "file_hashes": file_hashes,
                    "files": norm_paths,
                    "released": released,
                    "status": "success",
                    "summary": args.summary,
                    "task_id": args.task,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            f"[OK] Written off {len(norm_paths)} file(s) for agent '{args.agent}':"
        )
        for p in norm_paths:
            print(f"  - {p} (SHA256: {file_hashes.get(p, 'UNKNOWN')})")
        print(f"Summary: {args.summary}")
    return 0


def cmd_check(args, root_dir: str, state_dir: str, lock_path: str) -> int:
    norm_paths = [normalize_path(p, root_dir) for p in args.paths]
    with file_lock(lock_path):
        raw_leases = load_leases_raw(state_dir)
        leases, pruned = prune_expired_leases(raw_leases)
        if pruned > 0:
            save_leases(state_dir, leases)

        now = time.time()
        locked = []
        for p in norm_paths:
            if p in leases:
                cur = leases[p]
                rem = cur.get("expires_at", 0) - now
                if rem > 0:
                    locked.append({
                        "expires_at": cur.get("expires_at", 0),
                        "file": p,
                        "owner": cur.get("agent_id", "unknown"),
                        "remaining_ttl": round(rem, 2),
                        "task_id": cur.get("task_id", ""),
                    })

    if locked:
        if args.json:
            print(
                json.dumps(
                    {
                        "checked": norm_paths,
                        "locked": locked,
                        "status": "locked",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                f"[LOCKED] {len(locked)} of {len(norm_paths)} path(s) are currently locked:"
            )
            for item in locked:
                print(
                    f"  - {item['file']}: locked by '{item['owner']}' (TTL: {item['remaining_ttl']}s)"
                )
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "checked": norm_paths,
                    "locked": [],
                    "status": "unlocked",
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"[OK] All {len(norm_paths)} path(s) are unlocked.")
    return 0


def cmd_status(args, root_dir: str, state_dir: str, lock_path: str) -> int:
    with file_lock(lock_path):
        raw_leases = load_leases_raw(state_dir)
        leases, pruned = prune_expired_leases(raw_leases)
        if pruned > 0:
            save_leases(state_dir, leases)

        now = time.time()
        active_leases = {}
        for p, data in sorted(leases.items()):
            rem = round(max(0.0, data.get("expires_at", 0) - now), 2)
            item = dict(data)
            item["remaining_ttl"] = rem
            active_leases[p] = item

        journal_entries = read_journal_recent(state_dir, limit=args.limit)

    if args.json:
        print(
            json.dumps(
                {
                    "active_count": len(active_leases),
                    "active_leases": active_leases,
                    "journal": journal_entries,
                    "status": "success",
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("=== Agent Concurrency Status ===")
        print(f"Active Leases: {len(active_leases)}")
        for p, d in active_leases.items():
            print(
                f"  - {p}: agent='{d.get('agent_id')}', task='{d.get('task_id')}', remaining TTL={d.get('remaining_ttl')}s"
            )
        print(f"\nRecent Journal Entries (last {len(journal_entries)}):")
        for j in journal_entries:
            ts = j.get("timestamp", "")
            action = j.get("action", "")
            agent = j.get("agent_id", "")
            summary = j.get("summary", "")
            files = ", ".join(j.get("files", []))
            print(f"  [{ts}] {action.upper()} by {agent}: {summary} ({files})")
    return 0


def cmd_prune(args, root_dir: str, state_dir: str, lock_path: str) -> int:
    with file_lock(lock_path):
        raw_leases = load_leases_raw(state_dir)
        leases, pruned = prune_expired_leases(raw_leases)
        if pruned > 0:
            save_leases(state_dir, leases)

    if args.json:
        print(
            json.dumps(
                {
                    "pruned_count": pruned,
                    "remaining_count": len(leases),
                    "status": "success",
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            f"[OK] Pruned {pruned} expired lease(s). {len(leases)} active lease(s) remaining."
        )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="agent_lock",
        description="High-speed agent concurrency lease, locking, and journal manager.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Root directory of repository (default: repo root or AGENT_LOCK_ROOT env)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # acquire
    p_acquire = subparsers.add_parser("acquire", help="Acquire or refresh lease on paths")
    p_acquire.add_argument("paths", nargs="+", help="File paths to lease")
    p_acquire.add_argument("--agent", required=True, help="Agent identifier")
    p_acquire.add_argument("--task", default="", help="Task identifier")
    p_acquire.add_argument(
        "--ttl", type=float, default=300, help="Lease TTL in seconds (default: 300)"
    )
    p_acquire.add_argument("--summary", default="", help="Optional journal summary")
    p_acquire.add_argument("--force", action="store_true", help="Force preemption")
    p_acquire.add_argument("--json", action="store_true", help="Output structured JSON")
    p_acquire.add_argument("--root", default=None, help="Root directory")

    # release
    p_release = subparsers.add_parser("release", help="Release lease on paths")
    p_release.add_argument(
        "paths",
        nargs="*",
        help="File paths to release (empty for all agent's leases)",
    )
    p_release.add_argument("--agent", default="", help="Agent identifier")
    p_release.add_argument(
        "--force", action="store_true", help="Force release regardless of owner"
    )
    p_release.add_argument("--task", default="", help="Task identifier")
    p_release.add_argument("--json", action="store_true", help="Output structured JSON")
    p_release.add_argument("--root", default=None, help="Root directory")

    # write-off
    p_writeoff = subparsers.add_parser(
        "write-off",
        help="Write-off changes with SHA256 hashes and release leases",
    )
    p_writeoff.add_argument("paths", nargs="+", help="File paths to write-off")
    p_writeoff.add_argument("--agent", required=True, help="Agent identifier")
    p_writeoff.add_argument(
        "--summary", required=True, help="Summary description of changes"
    )
    p_writeoff.add_argument("--task", default="", help="Task identifier")
    p_writeoff.add_argument("--json", action="store_true", help="Output structured JSON")
    p_writeoff.add_argument("--root", default=None, help="Root directory")

    # check
    p_check = subparsers.add_parser("check", help="Check if paths are currently locked")
    p_check.add_argument("paths", nargs="+", help="File paths to check")
    p_check.add_argument("--json", action="store_true", help="Output structured JSON")
    p_check.add_argument("--root", default=None, help="Root directory")

    # status
    p_status = subparsers.add_parser(
        "status", help="Show active leases and recent journal entries"
    )
    p_status.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent journal entries (default: 10)",
    )
    p_status.add_argument("--json", action="store_true", help="Output structured JSON")
    p_status.add_argument("--root", default=None, help="Root directory")

    # prune
    p_prune = subparsers.add_parser("prune", help="Explicitly prune expired leases")
    p_prune.add_argument("--json", action="store_true", help="Output structured JSON")
    p_prune.add_argument("--root", default=None, help="Root directory")

    args = parser.parse_args(argv)

    tokens = sys.argv[1:] if argv is None else list(argv)
    is_json = bool(getattr(args, "json", False)) or ("--json" in tokens)
    args.json = is_json

    root_arg = getattr(args, "root", None)
    if not root_arg:
        for i, token in enumerate(tokens):
            if token == "--root" and i + 1 < len(tokens):
                root_arg = tokens[i + 1]
                break
            elif token.startswith("--root="):
                root_arg = token.split("=", 1)[1]
                break

    root_dir = find_repo_root(root_arg)
    state_dir = get_state_dir(root_dir)
    lock_path = os.path.join(state_dir, ".lock")

    if args.subcommand == "acquire":
        return cmd_acquire(args, root_dir, state_dir, lock_path)
    elif args.subcommand == "release":
        return cmd_release(args, root_dir, state_dir, lock_path)
    elif args.subcommand == "write-off":
        return cmd_write_off(args, root_dir, state_dir, lock_path)
    elif args.subcommand == "check":
        return cmd_check(args, root_dir, state_dir, lock_path)
    elif args.subcommand == "status":
        return cmd_status(args, root_dir, state_dir, lock_path)
    elif args.subcommand == "prune":
        return cmd_prune(args, root_dir, state_dir, lock_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
