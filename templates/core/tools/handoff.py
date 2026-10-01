#!/usr/bin/env python3
"""
handoff.py - Cross-agent session handoff.

Agents have different quotas. When one runs out mid-task, the next one should
not start from zero: it should read the recorded state and continue. This writes
a machine-readable snapshot (.harness/state.json) plus a copy-pasteable resume
brief, and auto-detects which IDE/agent is currently running.

Usage:
    python core/tools/handoff.py save --task "Fix inventory sorting" \
        --next "Update sort key in inventory_service.gd" --next "Re-run lint"
    python core/tools/handoff.py show
    python core/tools/handoff.py load            # resume brief for another agent
    python core/tools/handoff.py show --json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent.parent
STATE_DIR = PROJECT_ROOT / ".harness"
STATE_FILE = STATE_DIR / "state.json"
SCHEMA_VERSION = 1

# Ordered most-specific first: several tools set generic vars.
AGENT_SIGNATURES = [
    ("Google Antigravity", "antigravity", ("ANTIGRAVITY", "ANTI_GRAVITY", "GRAVITY")),
    ("Cursor", "cursor", ("CURSOR_TRACE_ID", "CURSOR_AGENT", "CURSOR_SESSION")),
    ("Claude Code", "claude_code", ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT")),
    ("Codex CLI", "codex", ("CODEX_SANDBOX", "CODEX_HOME", "CODEX_SESSION")),
    ("GitHub Copilot", "copilot", ("COPILOT_", "GITHUB_COPILOT")),
    ("Windsurf", "windsurf", ("WINDSURF",)),
    ("Aider", "aider", ("AIDER_",)),
    ("Continue", "continue", ("CONTINUE_",)),
]

GO_AGENT_DIRS = {
    ".cursor": "Cursor",
    ".windsurf": "Windsurf",
    ".aider": "Aider",
    ".continue": "Continue",
}


def detect_agent() -> dict:
    """Best-effort: environment signature first, then IDE marker dirs."""
    env = os.environ
    name, key = "unknown", ""
    for label, agent_key, prefixes in AGENT_SIGNATURES:
        if any(p in env for p in prefixes):
            name, key = label, agent_key
            break

    detected_dirs = []
    for d in AGENT_SIGNATURES:
        if name != "unknown" and d[1] == key:
            continue
    for marker in sorted(p.name for p in PROJECT_ROOT.iterdir()
                         if p.is_dir() and p.name in GO_AGENT_DIRS) if PROJECT_ROOT.exists() else []:
        detected_dirs.append(GO_AGENT_DIRS[marker])

    model = next((env[k] for k in ("ANTHROPIC_MODEL", "OPENAI_MODEL", "COPILOT_MODEL",
                                   "CODEX_MODEL", "GEMINI_MODEL")
                  if env.get(k)), "")
    return {"name": name, "key": key, "model": model,
            "ide_markers": detected_dirs}


def git(*args) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=str(PROJECT_ROOT),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_state() -> dict:
    status = git("status", "--porcelain")
    dirty = [ln[3:].strip().strip('"') for ln in status.splitlines() if len(ln) > 3]
    return {
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(dirty),
        "changed_files": dirty[:40],
        "recent_commits": [c for c in git("log", "--oneline", "-5").splitlines() if c],
    }


def project_facts() -> dict:
    pg = PROJECT_ROOT / "project.godot"
    facts = {"name": PROJECT_ROOT.name, "engine": "", "renderer": "",
             "main_scene": "", "autoloads": [], "resolution": ""}
    if not pg.is_file():
        return facts
    text = pg.read_text(encoding="utf-8", errors="ignore")

    def find(key, pattern=r'"([^"]+)"'):
        m = re.search(rf'{key}\s*=\s*{pattern}', text)
        return m.group(1) if m else ""

    facts["name"] = find("config/name") or facts["name"]
    facts["renderer"] = find("renderer/rendering_method")
    facts["main_scene"] = find("run/main_scene")
    m = re.search(r'config/features\s*=\s*PackedStringArray\(([^)]*)\)', text)
    if m:
        v = re.search(r'"(\d+\.\d+)"', m.group(1))
        facts["engine"] = f"Godot {v.group(1)}" if v else ""
    m = re.search(r'window/size/viewport_width\s*=\s*(\d+)[\s\S]*?viewport_height\s*=\s*(\d+)', text)
    if m:
        facts["resolution"] = f"{m.group(1)}x{m.group(2)}"
    section = re.search(r'\[autoload\]([\s\S]*?)(?=\n\[|\Z)', text)
    if section:
        facts["autoloads"] = re.findall(r'^\s*([A-Za-z_]\w*)\s*=', section.group(1), re.M)
    return facts


def verification() -> dict:
    """Cheap: lint only. Sweep is opt-in via --verify."""
    lint = TOOLS_DIR / "tscn_lint.py"
    if not lint.is_file():
        return {}
    try:
        p = subprocess.run([sys.executable, str(lint), "--json"],
                           cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
        try:
            issues = json.loads(p.stdout or "[]")
        except json.JSONDecodeError:
            issues = []
        return {"lint_clean": not issues, "lint_issues": len(issues)}
    except (OSError, subprocess.TimeoutExpired):
        return {}


def cmd_save(args) -> int:
    prev = {}
    if STATE_FILE.is_file():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}

    agent = detect_agent()
    if args.agent:
        agent["name"] = args.agent
        agent["key"] = re.sub(r"[^a-z0-9]+", "_", args.agent.lower()).strip("_")
    if args.ide:
        agent["ide"] = args.ide

    tasks = [args.task] if args.task else []
    steps = list(args.next or [])
    if not tasks and prev.get("task"):
        tasks = [prev["task"]]
    if not steps:
        steps = prev.get("next_steps", [])

    state = {
        "schema": SCHEMA_VERSION,
        "session_id": args.session or f"{agent['key']}-{uuid.uuid4().hex[:8]}",
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "project": project_facts(),
        "git": git_state(),
        "task": tasks[0] if tasks else "",
        "next_steps": steps,
        "verification": verification() if args.verify else prev.get("verification", {}),
        "rules": {
            "agents_md": (PROJECT_ROOT / "AGENTS.md").is_file(),
            "rules_dir": (PROJECT_ROOT / ".agents" / "rules").is_dir(),
            "skills_dir": (PROJECT_ROOT / ".agents" / "skills").is_dir(),
        },
        "tooling": {
            "cli": "python game.py",
            "commands": ["info", "lint", "sweep", "capture", "audit",
                         "validate", "syntax --scan .", "test"],
        },
        "previous_agent": prev.get("agent", {}).get("name", ""),
        "previous_session": prev.get("session_id", ""),
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if args.resume:
        print(brief(state))
    else:
        print(f"Saved handoff to {STATE_FILE.relative_to(PROJECT_ROOT)}")
        print(f"  session:  {state['session_id']}")
        print(f"  agent:    {agent['name']}")
        print(f"  task:     {state['task'] or '(none recorded)'}")
        print(f"  next:     {len(steps)} step(s)")
        print(f"\nResume elsewhere with:  python game.py handoff load")
    return 0


def brief(state: dict) -> str:
    g, p = state.get("git", {}), state.get("project", {})
    a = state.get("agent", {})
    L = [
        "# Session Handoff",
        "",
        f"Resuming: {state.get('task') or 'unspecified task'}",
        f"Previous agent: {a.get('name', 'unknown')}"
        + (f" (was {state['previous_agent']})" if state.get("previous_agent") else ""),
        f"Session: {state.get('session_id')}  Updated: {state.get('updated_utc')}",
        "",
        "## Project",
        f"- {p.get('name')} - {p.get('engine')} - {p.get('renderer')} renderer"
        f" - {p.get('resolution')}",
        f"- Main scene: `{p.get('main_scene') or '(none set)'}`",
    ]
    if p.get("autoloads"):
        L.append(f"- Autoloads: {', '.join(p['autoloads'])}")
    L += ["", "## Git State (verify before changing anything)"]
    L.append(f"- Branch `{g.get('branch')}` at `{g.get('head')}`"
             + ("  [UNCOMMITTED CHANGES]" if g.get("dirty") else ""))
    for c in g.get("recent_commits", [])[:3]:
        L.append(f"  - {c}")
    if g.get("changed_files"):
        L.append("- Uncommitted files:")
        L += [f"  - {f}" for f in g["changed_files"][:20]]

    L += ["", "## Next Steps"]
    if state.get("next_steps"):
        L += [f"{i}. {s}" for i, s in enumerate(state["next_steps"], 1)]
    else:
        L.append("1. (none recorded - ask the previous agent what to do next)")

    v = state.get("verification") or {}
    if v:
        L += ["", "## Verification"]
        L.append(f"- lint: {'clean' if v.get('lint_clean') else f'{v.get(legit_issues_key(v))} issue(s)'}"
                 if v else "- lint: not run")

    L += ["", "## Ground Rules (read before editing)"]
    L.append(f"- AGENTS.md present: {state.get('rules', {}).get('agents_md')}")
    L.append("- UI must be authored in .tscn, never built in GDScript.")
    L.append("- Do NOT add a second Godot runner; extend the existing one.")
    L += ["", "## Commands",
          "```bash", "python game.py info", "python game.py lint",
          "python game.py sweep", "python game.py capture --scene res://<scene>.tscn",
          "python game.py audit", "```"]
    return "\n".join(L)


def legit_issues_key(v: dict) -> str:
    return str(v.get("lint_issues", 0))


def cmd_load(args) -> int:
    if not STATE_FILE.is_file():
        print("No handoff recorded yet. Start one with:")
        print("  python game.py handoff save --task \"...\" --next \"...\"")
        return 1
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    if state.get("schema") != SCHEMA_VERSION:
        print(f"Warning: state schema v{state.get('schema')} != v{SCHEMA_VERSION}.")
    print(brief(state))
    return 0


def cmd_show(args) -> int:
    if not STATE_FILE.is_file():
        print("No handoff recorded yet.")
        return 1
    text = STATE_FILE.read_text(encoding="utf-8")
    print(text if args.json else brief(json.loads(text)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-agent session handoff")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("save", help="record the current state")
    s.add_argument("--task", help="what this session is doing")
    s.add_argument("--next", action="append", help="next step (repeatable)")
    s.add_argument("--agent", help="override detected agent name")
    s.add_argument("--ide", help="which IDE you are in (Cursor, VS Code, ...)")
    s.add_argument("--session", help="reuse an existing session id")
    s.add_argument("--verify", action="store_true", help="also run the linter")
    s.add_argument("--resume", action="store_true", help="print the resume brief")

    l = sub.add_parser("load", help="print a resume brief for another agent")
    d = sub.add_parser("show", help="show the recorded state")
    d.add_argument("--json", action="store_true")

    args = ap.parse_args()
    if args.cmd == "save":
        return cmd_save(args)
    if args.cmd == "load":
        return cmd_load(args)
    if args.cmd == "show":
        return cmd_show(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())