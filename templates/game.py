#!/usr/bin/env python3
"""Godot project tools. Standard library only; JSON stdout is an agent contract."""
import argparse
import concurrent.futures
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import signal
import subprocess
import struct
import sys
import tempfile
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TOOLS_DIR = PROJECT_ROOT / "core" / "tools"
CORE_RUNNER = TOOLS_DIR / "scene_runner.gd"
DOCS_UPDATER = TOOLS_DIR / "docs_updater.py"
SKIP_DIRS = {
    ".agents", ".agent", ".agent-state", ".context", ".harness", ".godot", ".git",
    ".venv", "venv", "addons", "artifacts", "builds", "screenshots", "graphify-out",
    "qa-evidence", "__pycache__",
}
ENGINE_ERRORS = re.compile(r"(?m)^\s*(?:SCRIPT ERROR:|ERROR:|Parse Error:)|Assertion failed")


def temp_directory(prefix):
    kwargs = {"ignore_cleanup_errors": True} if sys.version_info >= (3, 10) else {}
    return tempfile.TemporaryDirectory(prefix=prefix, **kwargs)


class HarnessError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise HarnessError("INVALID_ARGUMENT", message)


FIX_HINTS = {
    "BOM_FOUND": "Save file as UTF-8 without BOM signature.",
    "FORMAT_UNSUPPORTED": "Convert scene to Godot 4 format ([gd_scene format=3]).",
    "MISSING_RESOURCE": "Restore missing resource file or correct the ExtResource path.",
    "UNDECLARED_RESOURCE_ID": "Ensure resource is declared with [ext_resource] or [sub_resource] before reference.",
    "CORRUPTED_BYTE_ARRAY": "Re-export resource or correct PackedByteArray format.",
    "BROKEN_UID_REFERENCE": "Update uid:// to match existing resource or re-import in Godot.",
    "REPO_HYGIENE_DIRTY": "Clean ephemeral files with python game.py clean --all.",
    "SYNTAX_ERROR": "Check script syntax at line.",
    "COMMAND_FAILED": "Inspect stderr logs and fix the script error.",
    "UNREFERENCED_RESOURCE": "Delete unused asset file or wire it into a scene/code.",
    "DEAD_COLLISION_MASK": "Update collision_mask to match an active physics layer in project.godot.",
    "MISSING_COLLIDER": "Add a CollisionShape2D/3D child with an active Shape resource.",
    "MISSING_YSORT": "Enable y_sort_enabled on parent Node2D/TileMapLayer.",
    "HARDCODED_MAGIC_NUMBER": "Expose property with @export instead of hardcoding gameplay constant.",
    "DISCONNECTED_SIGNAL": "Ensure signal target method exists on receiver script.",
    "EXPENSIVE_PROCESS_CALL": "Cache nodes or results in _ready() instead of calling in _process().",
    "CHECKPOINT_FAILED": "Check write permissions for docs/harness/CHECKPOINT.md.",
    "ASSET_FRINGE_DETECTED": "Run python game.py assets --process <file> --defringe to clean matte fringe.",
    "ASSET_NOT_GRID_ALIGNED": "Resize image dimensions to be divisible by native grid size.",
    "ASSET_RUBRIC_BELOW_THRESHOLD": "Improve asset aesthetic fit, style, or composition to score >= 8.5.",
    "GRAPH_NOT_FRESH": "Run python game.py graph --refresh --json to rebuild graph.",
    "INVALID_ARGUMENT": "Check CLI command arguments and usage with --help.",
    "ART_STYLE_DIRECTION_UNSET": "Explicitly ask the user to decide and define their art & UI style direction before creating mockups or UI assets.",
    "LOCK_CONFLICT": "Wait for the holding agent to release the file lease or coordinate disjoint file ownership.",
    "FILE_LOCKED": "File is currently leased by another active agent; check status with python game.py lock status --json.",
}

NEXT_COMMANDS = {
    "plan-task": "python game.py scene-outline <scene.tscn> --json",
    "scene-outline": "view targeted line slice or python game.py syntax --scan <file> --json",
    "mockup-dissect": "python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact",
    "mockup-grade": "python game.py capture --json --compact",
    "syntax": None,
    "test": None,
    "capture": None,
    "audit": None,
    "baseline": None,
    "validate": None,
    "context": None,
    "assets": None,
    "saves": None,
    "clean": None,
    "info": None,
    "lock": None,
    "graph": None,
}

ACTIVE_SKILLS = {
    "info": ".agents/skills/token-budget/SKILL.md",
    "plan-task": ".agents/skills/core-architecture/SKILL.md",
    "scene-outline": ".agents/skills/core-architecture/SKILL.md",
    "mockup-dissect": ".agents/skills/ui-mockup-pipeline/SKILL.md",
    "mockup-grade": ".agents/skills/ui-mockup-pipeline/SKILL.md",
    "capture": ".agents/skills/ui-mockup-pipeline/SKILL.md",
    "baseline": ".agents/skills/godot-test-qa/SKILL.md",
    "assets": ".agents/skills/ui-mockup-pipeline/SKILL.md",
    "test": ".agents/skills/godot-test-qa/SKILL.md",
    "validate": ".agents/skills/godot-test-qa/SKILL.md",
    "audit": ".agents/skills/core-architecture/SKILL.md",
    "saves": ".agents/skills/core-architecture/SKILL.md",
    "syntax": ".agents/skills/gdscript-migration/SKILL.md",
    "graph": ".agents/skills/graphify/SKILL.md",
    "context": ".agents/skills/token-budget/SKILL.md",
    "clean": ".agents/skills/token-budget/SKILL.md",
    "lock": ".agents/skills/agent-coordination/SKILL.md",
}


def _to_posix(value):
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str):
        if value.startswith(("res://", "user://", "uid://", "http://", "https://")):
            return value
        if "\\" in value:
            return value.replace("\\", "/")
    return value


def _normalize_posix_payload(obj):
    if isinstance(obj, dict):
        return {k: _normalize_posix_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_posix_payload(v) for v in obj]
    return _to_posix(obj)


def compute_ctx_hash(root, engine_version=""):
    pg = Path(root) / "project.godot"
    if pg.is_file():
        st = pg.stat()
        raw = f"{st.st_mtime_ns}:{st.st_size}:{engine_version}"
    else:
        raw = f"missing:{engine_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def sync_project_state_cache(root, context_dict=None):
    """Cache discovery payload in .context/project_state.json and return (ctx_hash, ctx_stale, cached_context)."""
    root = Path(root)
    state_file = root / ".context" / "project_state.json"
    pg = root / "project.godot"
    pg_stat = pg.stat() if pg.is_file() else None
    pg_mtime = pg_stat.st_mtime_ns if pg_stat else 0
    pg_size = pg_stat.st_size if pg_stat else 0

    had_state_file = state_file.is_file()
    cached = {}
    if had_state_file:
        try:
            cached = json.loads(state_file.read_text(encoding="utf-8"))
            if not isinstance(cached, dict):
                cached = {}
        except Exception:
            cached = {}

    engine_ver = ""
    if context_dict and context_dict.get("engine_version"):
        engine_ver = str(context_dict["engine_version"])
    elif cached.get("engine_version"):
        engine_ver = str(cached["engine_version"])

    art_style = ""
    if context_dict and isinstance(context_dict.get("art_style_direction"), str) and context_dict["art_style_direction"].strip():
        art_style = context_dict["art_style_direction"].strip()
    elif isinstance(cached.get("art_style_direction"), str):
        art_style = cached["art_style_direction"].strip()

    ctx_hash = compute_ctx_hash(root, engine_ver)
    same_pg = (
        had_state_file
        and cached.get("project_godot_mtime_ns") == pg_mtime
        and cached.get("project_godot_size") == pg_size
        and cached.get("ctx_hash") == ctx_hash
    )
    has_full_context = bool(context_dict and "engine_version" in context_dict and "authored_settings" in context_dict)

    merged_context = dict(cached.get("context")) if isinstance(cached.get("context"), dict) else {}
    if context_dict and isinstance(context_dict, dict):
        merged_context.update(_normalize_posix_payload(context_dict))
    if not merged_context:
        merged_context = {"project_root": _to_posix(root)}

    if not had_state_file or has_full_context:
        payload = {
            "art_style_direction": art_style,
            "context": _normalize_posix_payload(merged_context),
            "ctx_hash": ctx_hash,
            "engine_version": engine_ver,
            "project_godot_mtime_ns": pg_mtime,
            "project_godot_size": pg_size,
        }
        if pg.is_file() or had_state_file or has_full_context:
            try:
                state_file.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(state_file, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            except OSError:
                pass
        stale = False
    else:
        stale = not same_pg

    return ctx_hash, stale, merged_context


def result(command, summary, findings=None, artifacts=None, status=None, next_command=None, compact=False, **extra):
    findings = findings or []
    artifacts = [_to_posix(a) for a in (artifacts or [])]
    if compact:
        omitted_findings = max(0, len(findings) - 5)
        omitted_artifacts = max(0, len(artifacts) - 5)
        if omitted_findings:
            findings = findings[:5]
            extra["omitted_findings_count"] = omitted_findings
        if omitted_artifacts:
            artifacts = artifacts[:5]
            extra["omitted_artifacts_count"] = omitted_artifacts
        extra["compact"] = True

    resolved_status = status or ("failed" if findings else "success")
    if next_command is not None:
        resolved_next = next_command
    elif resolved_status == "success" and not findings:
        resolved_next = NEXT_COMMANDS.get(command) if command in ("mockup-dissect", "mockup-grade") else None
    else:
        parse_file = next(
            (f.get("file") for f in findings if f.get("file") and ("SYNTAX" in str(f.get("code", "")) or "Parse Error" in str(f.get("message", "")))),
            None,
        )
        if parse_file:
            resolved_next = f"python game.py syntax --scan {_to_posix(parse_file)} --json"
        elif findings and resolved_status != "success":
            resolved_next = f"Fix findings and run python game.py {command} --json"
        else:
            resolved_next = NEXT_COMMANDS.get(command)

    return dict(schema_version=1, command=command,
                status=resolved_status, context={},
                summary=summary, findings=findings, artifacts=artifacts,
                next_command=resolved_next, **extra)


def finding(code, message, fix_hint=None, **location):
    res = dict(code=code, message=message, **location)
    res["fix_hint"] = fix_hint or location.get("fix_hint") or FIX_HINTS.get(code, "Inspect relevant source file and fix finding.")
    return res


def execute(command, *, cwd=None, env=None, timeout=30, log=True):
    if not math.isfinite(timeout) or timeout <= 0:
        raise HarnessError("INVALID_ARGUMENT", "Timeout must be positive")
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   start_new_session=sys.platform != "win32",
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
        stdout, stderr = process.communicate(timeout=timeout)
        completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as exc:
        for partial in (exc.output, exc.stderr):
            if partial:
                print((partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial)[-3000:], file=sys.stderr)
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        phase = next((flag for flag in ("--import", "--script", "--version", "--help") if flag in command), "execution")
        if phase == "--script":
            phase += " " + Path(command[command.index(phase) + 1]).name
        raise HarnessError("TIMEOUT", f"Command timed out after {timeout}s: {command[0]} ({phase})") from exc
    except OSError as exc:
        raise HarnessError("LAUNCH_FAILED", f"Cannot launch {command[0]}: {exc}") from exc
    verbose = os.environ.get("GAME_VERBOSE") == "1"
    has_error = bool(completed.returncode or ENGINE_ERRORS.search(completed.stdout + completed.stderr))
    for log_output in (completed.stdout, completed.stderr):
        if log_output and (has_error or (log and verbose)):
            print(log_output.rstrip(), file=sys.stderr)
    return completed


def load_tool(name, root=None):
    candidates = []
    if root is not None:
        candidates.append(Path(root) / "core" / "tools" / (name + ".py"))
        candidates.append(Path(root) / "tools" / (name + ".py"))
    candidates.append(TOOLS_DIR / (name + ".py"))
    candidates.append(PROJECT_ROOT / "tools" / (name + ".py"))
    tool_path = next((c for c in candidates if c.is_file()), TOOLS_DIR / (name + ".py"))
    spec = importlib.util.spec_from_file_location("gdh_" + name, tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_godot_bin(explicit=None):
    requested = explicit or os.environ.get("GODOT4_BIN") or os.environ.get("GODOT_BIN")
    if requested:
        binary = shutil.which(requested)
        if not binary:
            raise HarnessError("ENGINE_NOT_FOUND", f"Invalid selected engine: {requested}. Set --godot to an executable.")
        return binary
    for name in ("godot4", "godot", "Godot"):
        binary = shutil.which(name)
        if binary:
            return binary
    candidates = sorted((Path.home() / "Desktop").glob("Godot*.exe"))
    if len(candidates) == 1:
        return str(candidates[0])
    if len(candidates) > 1:
        raise HarnessError("ENGINE_AMBIGUOUS", "Multiple Desktop engines found; choose --godot explicitly")
    raise HarnessError("ENGINE_NOT_FOUND", "No Godot executable found; set --godot or GODOT4_BIN")


def project_files(root, suffix):
    return sorted(p for p in root.rglob("*" + suffix)
                  if not SKIP_DIRS.intersection(p.relative_to(root).parts)
                  and not p.is_relative_to(TOOLS_DIR) and not p.is_relative_to(root / "core" / "tools")
                  and p.resolve().is_relative_to(root))


def get_graphify_bin(root):
    local = root / ".harness" / "venv" / ("Scripts/graphify.exe" if sys.platform == "win32" else "bin/graphify")
    return str(local) if local.is_file() else shutil.which("graphify")


def project_path(root, value):
    path = Path(value.removeprefix("res://"))
    path = resolved_path(root / path)
    if not path.is_relative_to(root):
        raise HarnessError("OUTSIDE_PROJECT", f"Path must stay inside the project: {value}")
    if not path.exists():
        raise HarnessError("PATH_NOT_FOUND", f"Path does not exist: {path}")
    return path


def discover_tests(root):
    return [p for p in project_files(root / "tests", ".gd") if p.name.startswith("test_")] if (root / "tests").exists() else []


def resolve_project(explicit=None, required=True):
    candidates = [resolved_path(Path(explicit))] if explicit else [PROJECT_ROOT, Path.cwd(), *Path.cwd().parents]
    for root in candidates:
        if (root / "project.godot").is_file():
            return root.resolve()
    if not required:
        return (resolved_path(Path(explicit)) if explicit else Path.cwd()).resolve()
    raise HarnessError("PROJECT_NOT_FOUND", "No project.godot found; select a game with --project <directory>")


def engine_json(completed):
    errors = command_findings(completed, "Engine probe")
    if errors:
        raise HarnessError("ENGINE_PROBE_FAILED", errors[0]["message"] + "\n" + completed.stderr[-2000:])
    for line in completed.stdout.splitlines():
        if line.startswith("HARNESS_JSON="):
            return json.loads(line.removeprefix("HARNESS_JSON="))
    raise HarnessError("ENGINE_PROBE_FAILED", "Engine did not return probe JSON")


def inspect_context(root, explicit=None, timeout=30):
    binary = get_godot_bin(explicit)
    probe = execute([binary, "--version"], timeout=timeout, log=False)
    version = probe.stdout.strip()
    if probe.returncode or not re.match(r"^4\.\d+", version):
        raise HarnessError("ENGINE_UNSUPPORTED", f"Expected a Godot 4 executable; got {version or probe.stderr}")
    help_result = execute([binary, "--help"], timeout=timeout, log=False)
    if help_result.returncode:
        raise HarnessError("ENGINE_PROBE_FAILED", "Engine --help failed")
    flags = sorted(set(re.findall(r"--[\w-]+", help_result.stdout)) & {"--headless", "--script", "--path", "--import", "--check-only", "--rendering-method", "--audio-driver", "--version", "--help"})
    if "--headless" not in flags or "--script" not in flags:
        raise HarnessError("ENGINE_UNSUPPORTED", "Selected engine lacks --headless/--script")
    with temp_directory(prefix="gdh-probe-") as scratch:
        Path(scratch, "project.godot").write_text("config_version=5\n", encoding="utf-8")
        env = {"GAME_PROJECT_CONFIG": str(root / "project.godot")}
        completed = run_headless_godot(["--script", str(TOOLS_DIR / "project_probe.gd")], env,
                                      root=Path(scratch), godot=binary, timeout=max(timeout, 15))
        settings = engine_json(completed)
    source = "argument" if explicit else "environment" if os.environ.get("GODOT4_BIN") or os.environ.get("GODOT_BIN") else "discovery"
    hint = next((v for v in settings["features"] if re.fullmatch(r"4\.\d+(?:\.\d+)?", str(v))), None)
    note = "Runtime compatibility is unverified; project feature tags are hints, not engine detection"
    if hint and tuple(map(int, version.split(".")[:2])) < tuple(map(int, hint.split(".")[:2])):
        note = "Selected engine is older than the project's version hint; verify compatibility before development"
    return dict(project_root=str(root), engine_binary=binary, engine_source=source,
                engine_version=version, engine_flags=flags, authored_settings=settings,
                project_version_hint=hint, compatibility_note=note)


def capabilities(args):
    tools = []
    for name, parser in args.commands.items():
        available = True
        reason = None
        if name == "capture":
            available = CORE_RUNNER.is_file() and sys.platform in ("win32", "linux")
            reason = "Rendering is unverified until a real capture succeeds" if available else "Capture runner or platform save-profile isolation is unavailable"
        if name == "graph":
            available = get_graphify_bin(args.root) is not None
            reason = "Graphify is missing; propose dependency installation in a reviewed setup plan" if not available else None
        if name == "test":
            available = sys.platform in ("win32", "linux")
            reason = None if available else "Test execution save-profile isolation is not implemented on this platform"
        tools.append(dict(name=name, description=parser.description, available=available,
                          unavailable_reason=None if available else reason, verification_note=reason,
                          mutating=name in ("capture", "test", "validate", "syntax", "graph", "context", "clean", "lock", "mockup-dissect"),
                          mutation_condition={"syntax": "Only --learn-* modifies rules; --scan records an outcome", "graph": "--refresh rebuilds project graph/state", "context": "--refresh updates managed context", "test": "Execution writes isolated user data and a checkpoint", "capture": "Writes capture artifacts and a checkpoint", "validate": "Writes a checkpoint; engine execution may write caches", "clean": "Deletes ephemeral screenshots and QA review evidence", "lock": "Acquires, releases, or journals advisory file leases in .agent-state/", "mockup-dissect": "Writes dissection_manifest.json and crops in artifacts/ui_pipeline/"}.get(name),
                          arguments=[dict(flags=a.option_strings, required=a.required,
                                          default={"timeout": 30, "json": False}.get(a.dest, None) if a.default == argparse.SUPPRESS else a.default,
                                          type="array" if a.nargs in ("+", "*") else "boolean" if a.nargs == 0 else {int: "integer", float: "number"}.get(a.type, "string"), choices=a.choices)
                                     for a in parser._actions if a.option_strings and a.dest != "help"]))
    return tools


def fingerprint(root):
    digest = hashlib.sha256()
    paths = {root / "project.godot"}
    for suffix in (".gd", ".tscn", ".tres", ".gdshader", ".cs", ".py", ".cfg"):
        paths.update(project_files(root, suffix))
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def resolved_path(path):
    resolved = path.resolve()
    # Windows realpath can retain an extended prefix when an atomic replacement races its second lookup.
    # Both spellings name the same resolved file; normalize before containment comparisons.
    if sys.platform == "win32":
        value = str(resolved)
        if value.startswith("\\\\?\\UNC\\"):
            resolved = Path("\\\\" + value[8:])
        elif value.startswith("\\\\?\\"):
            resolved = Path(value[4:])
    return resolved


def safe_target(root, relative):
    path = resolved_path(root / relative)
    if not path.is_relative_to(root):
        raise HarnessError("OUTSIDE_PROJECT", f"Managed path escapes the project: {relative} (resolved {path}; root {root})")
    return path


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def merge_managed(existing, body):
    start, end = "<!-- GODOT-HARNESS:BEGIN -->", "<!-- GODOT-HARNESS:END -->"
    block = start + "\n" + body.strip() + "\n" + end
    if start not in existing and end not in existing:
        return existing.rstrip() + ("\n\n" if existing.strip() else "") + block + "\n"
    if existing.count(start) != 1 or existing.count(end) != 1 or existing.index(start) > existing.index(end):
        raise HarnessError("CONTEXT_CONFLICT", "Malformed or duplicate managed Markdown block; preserve and review manually")
    return existing[:existing.index(start)] + block + existing[existing.index(end) + len(end):]


def graph_state(root):
    graph = safe_target(root, "graphify-out/graph.json")
    state_file = safe_target(root, ".harness/graph-state.json")
    if not graph.is_file():
        return {"status": "missing", "hint": "Run python game.py graph --refresh --json"}
    if not state_file.is_file():
        return {"status": "untracked", "hint": "Refresh once to establish source freshness"}
    state = json.loads(state_file.read_text(encoding="utf-8"))
    fresh = state.get("source_digest") == fingerprint(root) and state.get("graph_digest") == hashlib.sha256(graph.read_bytes()).hexdigest()
    return {"status": "fresh" if fresh else "stale", "path": str(graph)}


def cmd_graph(args):
    binary = get_graphify_bin(args.root)
    if not binary:
        raise HarnessError("TOOL_UNAVAILABLE", "Graphify is missing; review a setup plan with --graphify install")
    graph = safe_target(args.root, "graphify-out/graph.json")
    if args.refresh:
        digest = fingerprint(args.root)
        backup = None
        state_file = safe_target(args.root, ".harness/graph-state.json")
        if graph.is_file():
            previous = graph.read_text(encoding="utf-8")
            previous_digest = hashlib.sha256(graph.read_bytes()).hexdigest()
            tracked = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}
            if tracked.get("graph_digest") != previous_digest:
                backup = safe_target(args.root, ".harness/graph-backups/" + previous_digest + ".json")
                atomic_write(backup, previous)
        godot_files = [p for suffix in (".gd", ".tscn", ".tres") for p in project_files(args.root, suffix)]
        data = load_tool("godot_graph").extract(args.root, godot_files, load_tool("docs_updater").code_text)
        native_files = [p for suffix in (".py", ".cs") for p in project_files(args.root, suffix) if p != args.root / "game.py"]
        if native_files:
            with temp_directory(prefix="gdh-graph-") as scratch:
                for path in native_files:
                    target = Path(scratch) / path.relative_to(args.root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                completed = execute([binary, "update", scratch, "--no-cluster"], cwd=scratch, timeout=args.timeout)
                failures = command_findings(completed, "Graphify AST update")
                if failures:
                    return result("graph", "Graph update failed; freshness was not recorded", failures)
                native = json.loads(Path(scratch, "graphify-out/graph.json").read_text(encoding="utf-8"))
                if native.get("failed_sources"):
                    raise HarnessError("GRAPH_UPDATE_INCOMPLETE", "Graphify could not parse all selected Python/C# files")
                data["nodes"].extend(native["nodes"])
                data["links"].extend(native.get("links", []))
        if digest != fingerprint(args.root):
            raise HarnessError("GRAPH_UPDATE_INCOMPLETE", "Sources changed during graph update; retry")
        atomic_write(graph, json.dumps(data, indent=2, sort_keys=True) + "\n")
        atomic_write(safe_target(args.root, ".harness/graph-state.json"), json.dumps(
            {"source_digest": digest, "graph_digest": hashlib.sha256(graph.read_bytes()).hexdigest()}, indent=2, sort_keys=True) + "\n")
        return result("graph", "Graph refreshed; Godot source index + Python/C# AST, not runtime proof", artifacts=[str(graph)] + ([str(backup)] if backup else []), nodes=len(data["nodes"]),
                      coverage="Godot declarations, scene nodes and explicit res:// references; Python/C# AST. Dynamic paths, signal wiring and shaders require direct inspection.")
    state = graph_state(args.root)
    if not args.query:
        return result("graph", "Persistent graph status", graph=state)
    if state["status"] != "fresh":
        raise HarnessError("GRAPH_NOT_FRESH", "Refresh the missing/stale/untracked graph before querying")
    if args.budget <= 0:
        raise HarnessError("INVALID_ARGUMENT", "Query token budget must be positive")
    completed = execute([binary, "query", args.query, "--budget", str(args.budget)], cwd=args.root, timeout=args.timeout, log=False)
    limit = args.budget * 4
    output = completed.stdout[:limit]
    truncated = len(completed.stdout) > limit
    if truncated:
        output = output.rsplit("\n", 1)[0]
    return result("graph", "Scoped graph query" + ("; narrow the query to see omitted results" if truncated else ""),
                  command_findings(completed, "Graph query"), output=output, truncated=truncated,
                  output_char_limit=limit, budget_note="Graphify token budget is a hint; wrapper enforces a character cap")


def context_documents(root, context):
    settings = context.get("authored_settings", {})
    overview = "# Project overview\n\n" + "\n".join(
        f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        for key, value in sorted(settings.items())
    )
    overview += f"\n- Engine: {context.get('engine_version', 'not discovered')}\n- Scripts: {len(project_files(root, '.gd'))}; scenes: {len(project_files(root, '.tscn'))}\n\nAuthored settings are not runtime-effective overrides. Genre and architecture must be verified from source. Keep project-specific decisions outside this managed block."
    commands = """# Tool commands

Run from the project root. Use --project and --godot to override discovery. Prefer `--json --compact --out <file>` for deterministic UTF-8 output.

- python game.py plan-task "<task>" [--files <f1> <f2>] --json --compact: deterministic task planner, change classifier (`Minor` vs `Major`), required skill binder, playbook matcher, and art style gate.
- python game.py scene-outline <scene.tscn> --json --compact: compact node, script, property, and signal outline for .tscn scenes.
- python game.py mockup-dissect [--scene <scene.tscn>] [--mockup <mockup.png>] [--out-dir artifacts/ui_pipeline] [--check-prereqs] --json --compact: Stage 0/1 UI pipeline prerequisite check, 1D scanline bezel profiler, and Control bounds probe.
- python game.py mockup-grade [--manifest artifacts/ui_pipeline/dissection_manifest.json] [--tolerance 2.0] --json --compact: Stage 3 deterministic UI StyleBox margin, padding, alignment, and overlap grader.
- python game.py capture [--scene <scene> | --scenes <s1> <s2> | --all-scenes] [--clean] --json --compact: Stage 4 scene renderer and visual layout verifier (pre-purges tests/screenshots/).
- python game.py baseline [--save | --check] [--scene <scene>] --json --compact: save or check headless UI layout baselines for visual regression testing.
- python game.py audit [--physics] [--exports] [--signals] [--perf] [--scene-first] --json --compact: deep in-game logic, collision matrix, Y-sort, signal wiring, and frame-budget audit.
- python game.py assets [--audit | --process | --grade | --defringe | --crop-alpha] [<file>] --json --compact: audit sprite alpha, detect fringes, rescale, and grade 3-tier aesthetic rubric (>= 8.5 pass threshold).
- python game.py saves [--dir <dir>] --json --compact: inspect user:// save files, validate schemas, and debug data.
- python game.py validate [--engine] [--uid] [--orphans] --json --compact: scan Scene-First policy, UTF-8 BOM, and resource/UID references (--engine parses/loads resources).
- python game.py syntax [--scan <path> | --query <topic>] --json --compact: check GDScript migration hints or query/learn documentation rules.
- python game.py test [--changed | --tier <tier> | --suite <suite> | --list] --json --compact: discover and run recursive SceneTree test suites.
- python game.py lock {acquire,release,write-off,check,status,prune} [<files...>] [--agent <id>] [--task <task>] [--summary <text>] --json --compact: multi-agent advisory file lease manager and SHA-256 write-off journal.
- python game.py graph [--refresh | --query "<q>"] --json --compact: persistent AST knowledge graph status, refresh, or scoped query (Major changes only).
- python game.py context [--refresh] --json --compact: inspect or refresh persistent project guidance while preserving user notes.
- python game.py clean [--captures | --qa-evidence | --all | --audit] --json --compact: delete ephemeral debug captures, dangling temp/import files, and expired leases.
- python game.py info --json --compact: inspect cached project/engine state and tool capabilities.

Inspect status, findings and artifacts. skipped means no checks ran, not passed.
Capture needs graphics support and may open a rendering window. Engine checks may write caches; isolated user data is not a code sandbox. Asset-heavy projects need existing editor import metadata; this tool does not start the editor importer.
Batch results keep individual PNG/manifests and an HTML gallery; optional Pillow adds six-scene, three-column PNG sheets. Per-scene failures continue and make the batch fail. Components requiring parents/state need explicit setup; capture observes initial render frames.
Learned syntax notes stay inactive unless explicit --verified, --min-version, --max-version-exclusive, --matcher, --literal and --source-url evidence is provided.
"""
    return {"docs/harness/PROJECT.md": overview, "docs/harness/TOOLS.md": commands}


def cmd_context(args):
    if args.refresh:
        args.context.update(inspect_context(args.root, args.godot, args.timeout))
        for relative, body in context_documents(args.root, args.context).items():
            path = safe_target(args.root, relative)
            atomic_write(path, merge_managed(path.read_text(encoding="utf-8") if path.exists() else "", body))
        atomic_write(safe_target(args.root, ".harness/context-state.json"), json.dumps({"source_digest": fingerprint(args.root)}, sort_keys=True) + "\n")
    paths = [safe_target(args.root, p) for p in ("docs/harness/PROJECT.md", "docs/harness/TOOLS.md", "docs/harness/CHECKPOINT.md")]
    return result("context", "Persistent project context", artifacts=[str(p) for p in paths if p.is_file()], graph=graph_state(args.root))


def _sanitize_checkpoint_artifact(artifact_path, root):
    posix_val = _to_posix(artifact_path)
    try:
        p = Path(artifact_path)
        if p.is_absolute() and p.resolve().is_relative_to(root.resolve()):
            posix_val = p.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        pass
    posix_val = re.sub(r"capture-[a-zA-Z0-9_]+(?=/|$)", "capture-latest", posix_val)
    posix_val = re.sub(r"gdh-[a-zA-Z0-9_-]+(?=/|$)", "gdh-scratch", posix_val)
    return posix_val


def record_checkpoint(root, response):
    outcome = {k: response[k] for k in ("command", "status", "summary", "findings", "artifacts") if k in response}
    outcome["time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    outcome["source_digest"] = fingerprint(root)
    outcome["engine_version"] = response.get("context", {}).get("engine_version")
    if "next_command" in response:
        outcome["next_command"] = response["next_command"]
    atomic_write(safe_target(root, ".harness/checkpoint.json"), json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    path = safe_target(root, "docs/harness/CHECKPOINT.md")

    seen_findings = set()
    deduped_findings = []
    for f in outcome.get("findings", []):
        key = (f.get("code"), f.get("message"), _to_posix(f.get("file")), f.get("line"))
        if key not in seen_findings:
            seen_findings.add(key)
            deduped_findings.append(_normalize_posix_payload(f))

    capped_findings = deduped_findings[:5]
    omitted_f_count = len(deduped_findings) - len(capped_findings)
    artifacts = [_sanitize_checkpoint_artifact(a, root) for a in outcome.get("artifacts", [])]
    capped_artifacts = artifacts[:5]
    omitted_a_count = len(artifacts) - len(capped_artifacts)

    compact_outcome = {
        "artifacts": capped_artifacts,
        "command": outcome["command"],
        "findings": capped_findings,
        "next_command": outcome.get("next_command"),
        "status": outcome["status"],
        "summary": outcome["summary"],
    }
    if omitted_f_count > 0:
        compact_outcome["omitted_findings_count"] = omitted_f_count
    if omitted_a_count > 0:
        compact_outcome["omitted_artifacts_count"] = omitted_a_count

    body = "# Last tool outcome\n\n```json\n" + json.dumps(compact_outcome, indent=2, sort_keys=True) + "\n```\n\nThis records tool evidence only. It does not certify gameplay, device acceptance or IDE compliance. Add handoff notes outside the managed block."
    atomic_write(path, merge_managed(path.read_text(encoding="utf-8") if path.exists() else "", body))


def run_headless_godot(arguments, extra_env=None, capture_mode=False, *, root=PROJECT_ROOT, godot=None, timeout=30, renderer=None):
    if sys.platform not in ("win32", "linux") and arguments != ["--script", str(TOOLS_DIR / "project_probe.gd")]:
        raise HarnessError("ISOLATION_UNSUPPORTED", "Execution save-profile isolation is not implemented on this platform; configuration discovery remains available")
    env = os.environ.copy()
    with temp_directory(prefix="gdh-profile-") as profile:
        env.update(APPDATA=profile, LOCALAPPDATA=profile, XDG_DATA_HOME=profile,
                   XDG_CONFIG_HOME=profile, GAME_PROFILE_ROOT=profile)
        if extra_env:
            env.update(extra_env)
        flags = ["--audio-driver", "Dummy"] if capture_mode else ["--headless"]
        if renderer:
            flags += ["--rendering-method", renderer]
        if arguments != ["--script", str(TOOLS_DIR / "project_probe.gd")]:
            with temp_directory(prefix="gdh-user-data-probe-") as scratch:
                Path(scratch, "project.godot").write_text("config_version=5\n", encoding="utf-8")
                prepared = execute([godot or get_godot_bin(), "--path", scratch, "--headless", "--script", str(TOOLS_DIR / "project_probe.gd")],
                    cwd=scratch, env={**env, "GAME_PROJECT_CONFIG": str(root / "project.godot"), "GAME_PROFILE_CONFIG": str(Path(scratch, "project.godot"))}, timeout=timeout, log=False)
                if command_findings(prepared, "User-data configuration preflight"):
                    return prepared
                checked = execute([godot or get_godot_bin(), "--path", scratch, "--headless", "--script", str(TOOLS_DIR / "engine_check.gd")],
                                  cwd=scratch, env={**env, "GAME_CHECK_FILES": "[]"}, timeout=timeout, log=False)
                if command_findings(checked, "User-data isolation"):
                    return checked
        return execute([godot or get_godot_bin(), "--path", str(root), *flags, *arguments],
                       cwd=root, env=env, timeout=timeout)


def command_findings(completed, label, strict_leaks=False):
    combined = completed.stdout + completed.stderr
    if completed.returncode or ENGINE_ERRORS.search(combined):
        if completed.returncode == 0 and not strict_leaks:
            has_script_error = bool(re.search(r"(?m)^\s*(?:SCRIPT ERROR:|Parse Error:)", combined))
            if not has_script_error and ("resources still in use at exit" in combined or "ObjectDB instances leaked at exit" in combined):
                return []
        locations = sorted(set(re.findall(r"(res://[^()\r\n]+):(\d+)", combined)))
        if locations:
            return [finding("COMMAND_FAILED", f"{label} failed (exit {completed.returncode}); see stderr logs", file=path, line=int(line)) for path, line in locations]
        return [finding("COMMAND_FAILED", f"{label} failed (exit {completed.returncode}); see stderr logs")]
    return []


def cmd_info(args):
    if getattr(args, "compact", False) and not getattr(args, "full", False):
        _, stale_cache, cached_ctx = sync_project_state_cache(args.root)
        if not stale_cache and cached_ctx.get("engine_version"):
            args.context.update(cached_ctx)
        else:
            args.context.update(inspect_context(args.root, args.godot, args.timeout))
    else:
        args.context.update(inspect_context(args.root, args.godot, args.timeout))
    state = safe_target(args.root, ".harness/context-state.json")
    stale = not state.is_file() or json.loads(state.read_text(encoding="utf-8")).get("source_digest") != fingerprint(args.root)
    return result("info", "Project and engine discovered", capabilities=capabilities(args), graph=graph_state(args.root), context_stale=stale,
                  tests=[_to_posix(p.relative_to(args.root)) for p in discover_tests(args.root)],
                  runner_available=CORE_RUNNER.is_file())


def capture_scene(args, scene, output):
    if not scene:
        raise HarnessError("SCENE_REQUIRED", "Project has no main scene; supply --scene")
    if not scene.startswith("uid://"):
        scene_path = project_path(args.root, scene)
        if scene_path.suffix != ".tscn":
            raise HarnessError("INVALID_SCENE", "Capture requires a .tscn scene")
        scene = "res://" + scene_path.relative_to(args.root).as_posix()
    output.mkdir(parents=True, exist_ok=True)
    capture_id = uuid.uuid4().hex

    env_vars = {
        "GAME_TARGET_SCENE": scene,
        "GAME_OUTPUT_DIR": str(output),
        "GAME_VIEWPORT_WIDTH": str(getattr(args, "width", 0) or 0),
        "GAME_VIEWPORT_HEIGHT": str(getattr(args, "height", 0) or 0),
        "GAME_CAPTURE_ID": capture_id
    }
    props = getattr(args, "prop", None) or []
    if props:
        props_dict = {}
        for p in props:
            if "=" in p:
                k, v = p.split("=", 1)
                v_clean = v.strip()
                if v_clean.lower() == "true": val = True
                elif v_clean.lower() == "false": val = False
                elif re.match(r'^-?\d+$', v_clean): val = int(v_clean)
                elif re.match(r'^-?\d+\.\d+$', v_clean): val = float(v_clean)
                else: val = v_clean
                props_dict[k.strip()] = val
        env_vars["GAME_PROPERTIES"] = json.dumps(props_dict)

    inputs_arg = getattr(args, "inputs", None)
    input_file = getattr(args, "input_file", None)
    if input_file:
        input_path = project_path(args.root, input_file)
        env_vars["GAME_INPUTS"] = input_path.read_text(encoding="utf-8")
    elif inputs_arg:
        env_vars["GAME_INPUTS"] = inputs_arg

    fixed_fps = getattr(args, "fixed_fps", None)
    if fixed_fps:
        env_vars["GAME_FIXED_FPS"] = str(fixed_fps)

    completed = run_headless_godot(["--script", str(CORE_RUNNER)],
        env_vars,
        capture_mode=True, root=args.root, godot=args.context["engine_binary"], timeout=args.timeout, renderer=getattr(args, "renderer", None))
    findings = command_findings(completed, "Capture")
    if findings:
        return result("capture", "Capture failed; no visual proof", findings)
    png, manifest = output / "capture.png", output / "scene_manifest.json"
    if not png.is_file() or not manifest.is_file():
        raise HarnessError("ARTIFACT_WRITE_FAILED", "Capture did not produce both PNG and manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("capture_id") != capture_id or data.get("scene") != scene:
        raise HarnessError("ARTIFACT_INVALID", "Capture artifacts are stale or belong to another scene/call")
    with png.open("rb") as file:
        header = file.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or list(struct.unpack(">II", header[16:24])) != data["viewport"] or data["viewport"] != data["requested_viewport"]:
        raise HarnessError("ARTIFACT_INVALID", "PNG dimensions do not match the manifest")
    return result("capture", "Rendered PNG and matching manifest verified", artifacts=[str(png), str(manifest)],
                  capture=data, renderer_override=getattr(args, "renderer", None))


def safe_rmtree(path):
    """Safely remove a directory tree, clearing read-only attributes on Windows if necessary."""
    p = Path(path)
    if not p.exists():
        return
    def _handle_remove_readonly(func, target_path, exc_info):
        try:
            import stat
            os.chmod(target_path, stat.S_IWRITE)
            func(target_path)
        except Exception:
            pass
    shutil.rmtree(p, onerror=_handle_remove_readonly)


def prune_debug_captures(root, keep=5, purge_all=False):
    """Safely prune oldest debug capture directories, keeping at most `keep` recent runs."""
    parent = safe_target(root, "screenshots/debug")
    if not parent.is_dir():
        return [], 0
    deleted = []
    freed_bytes = 0
    try:
        entries = [p for p in parent.iterdir() if p.is_dir() and p.name.startswith("capture-")]
        entries.sort(key=lambda p: p.stat().st_mtime)
        target_count = 0 if purge_all else max(0, keep)
        while len(entries) > target_count:
            victim = entries.pop(0)
            for f in victim.rglob("*"):
                if f.is_file():
                    freed_bytes += f.stat().st_size
            safe_rmtree(victim)
            deleted.append(str(victim.relative_to(root)))
    except (OSError, PermissionError):
        pass
    return deleted, freed_bytes


def is_dangling_temp_file(p: Path, root: Path, in_gdignore=None) -> bool:
    if not p.is_file():
        return False
    if p.name == ".gdignore":
        return False
    lower = p.name.lower()
    if any(lower.endswith(ext) for ext in (".tmp", ".bak", ".swp", ".orig")) or p.name.endswith("~") or "-autosave" in p.name:
        return True
    if p.name.startswith("~$"):
        return True
    if p.name.endswith(".lock") and p.name != ".lock" and (".agent-state" in p.parts or "claims" in p.parts):
        return True
    if in_gdignore is None:
        try:
            in_gdignore = any((parent / ".gdignore").exists() for parent in p.parents if parent != root.parent)
        except Exception:
            in_gdignore = False
    if in_gdignore and (p.name.endswith(".import") or p.name.endswith(".translation") or p.name.endswith(".uid")):
        return True
    if p.name.endswith(".uid"):
        companion = p.parent / p.stem
        if not companion.exists():
            return True
    if p.name.endswith(".import"):
        companion = p.parent / p.stem
        if not companion.exists():
            return True
    return False


def find_dangling_temp_files(root: Path):
    dangling = []
    skip = {".git", ".godot", ".venv", "venv", "__pycache__", "node_modules"}
    gdignore_dirs = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        norm_dir = os.path.normpath(dirpath)
        if ".gdignore" in filenames:
            gdignore_dirs.add(norm_dir)
        in_gd = any(norm_dir == gd or norm_dir.startswith(gd + os.sep) for gd in gdignore_dirs)
        file_set = set(filenames)
        for f in filenames:
            p = Path(dirpath) / f
            if ".agent-state" in dirpath and f in ("leases.json", "journal.jsonl", ".lock"):
                continue
            lower = f.lower()
            if any(lower.endswith(ext) for ext in (".tmp", ".bak", ".swp", ".orig")) or f.endswith("~") or "-autosave" in f:
                dangling.append(p)
                continue
            if f.startswith("~$"):
                dangling.append(p)
                continue
            if f.endswith(".lock") and f != ".lock" and (".agent-state" in dirpath or "claims" in dirpath):
                dangling.append(p)
                continue
            if in_gd and (f.endswith(".import") or f.endswith(".translation") or f.endswith(".uid")):
                dangling.append(p)
                continue
            if f.endswith(".uid") and f[:-4] not in file_set:
                dangling.append(p)
                continue
            if f.endswith(".import") and f[:-7] not in file_set:
                dangling.append(p)
                continue
    return dangling


def prune_expired_leases(root: Path) -> int:
    """Auto-prune expired lease entries in .agent-state/leases.json."""
    leases_file = root / ".agent-state" / "leases.json"
    if not leases_file.is_file():
        return 0
    try:
        lock_mod = load_tool("agent_lock", root)
        if hasattr(lock_mod, "load_leases_raw") and hasattr(lock_mod, "prune_expired_leases") and hasattr(lock_mod, "save_leases"):
            state_dir = str(root / ".agent-state")
            lock_path = str(root / ".agent-state" / ".lock")
            with lock_mod.file_lock(lock_path):
                raw_leases = lock_mod.load_leases_raw(state_dir)
                if raw_leases:
                    valid, pruned = lock_mod.prune_expired_leases(raw_leases)
                    if pruned > 0:
                        lock_mod.save_leases(state_dir, valid)
                    return pruned
    except Exception:
        pass
    try:
        data = json.loads(leases_file.read_text(encoding="utf-8"))
    except Exception:
        return 0

    now = time.time()

    def is_expired(entry):
        if not isinstance(entry, dict):
            return False
        exp = entry.get("expires_at")
        if exp is None:
            return False
        if isinstance(exp, (int, float)):
            return exp < now
        if isinstance(exp, str):
            try:
                iso_clean = exp.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(iso_clean)
                return dt.timestamp() < now
            except Exception:
                try:
                    return float(exp) < now
                except Exception:
                    return False
        return False

    pruned = 0
    if isinstance(data, list):
        remaining = [item for item in data if not is_expired(item)]
        pruned = len(data) - len(remaining)
        if pruned > 0:
            leases_file.write_text(json.dumps(remaining, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif isinstance(data, dict):
        if "leases" in data and isinstance(data["leases"], list):
            remaining = [item for item in data["leases"] if not is_expired(item)]
            pruned = len(data["leases"]) - len(remaining)
            if pruned > 0:
                data["leases"] = remaining
                leases_file.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            remaining = {k: v for k, v in data.items() if not is_expired(v)}
            pruned = len(data) - len(remaining)
            if pruned > 0:
                leases_file.write_text(json.dumps(remaining, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return pruned


def cmd_clean(args):
    """Delete ephemeral debug screenshots and QA review evidence."""
    if getattr(args, "audit", False):
        prune_expired_leases(args.root)
        hygiene_findings = []
        dangling_files = find_dangling_temp_files(args.root)
        for df in dangling_files:
            hygiene_findings.append(finding("REPO_HYGIENE_DIRTY", f"Dangling temporary file: {df.relative_to(args.root)}",
                                            file=str(df.relative_to(args.root)), fix_hint="Remove temporary file: python game.py clean --all"))
        debug_dir = safe_target(args.root, "screenshots/debug")
        if debug_dir.is_dir() and any(debug_dir.iterdir()):
            count = len(list(debug_dir.iterdir()))
            hygiene_findings.append(finding("REPO_HYGIENE_DIRTY", f"{count} ephemeral capture directories present in screenshots/debug",
                                            fix_hint="Purge debug captures: python game.py clean --captures"))
        summary = "Repo hygiene audit clean" if not hygiene_findings else f"Repo hygiene audit found {len(hygiene_findings)} item(s) to clean"
        return result("clean", summary, hygiene_findings, status="success" if not hygiene_findings else "failed")

    deleted = []
    freed = 0
    clean_all = getattr(args, "all", False)
    clean_captures = getattr(args, "captures", False)
    clean_qa = getattr(args, "qa_evidence", False)
    if not clean_captures and not clean_qa and not clean_all:
        clean_captures = True

    if clean_captures or clean_all:
        d, b = prune_debug_captures(args.root, purge_all=True)
        deleted.extend(d)
        freed += b
        debug_dir = safe_target(args.root, "screenshots/debug")
        if debug_dir.is_dir():
            safe_rmtree(debug_dir)
            deleted.append("screenshots/debug")
        sc_dir = safe_target(args.root, "screenshots")
        if sc_dir.is_dir() and not any(sc_dir.iterdir()):
            safe_rmtree(sc_dir)
        tests_sc_dir = safe_target(args.root, "tests/screenshots")
        if tests_sc_dir.is_dir():
            for child in list(tests_sc_dir.iterdir()):
                if child.is_dir():
                    safe_rmtree(child)
                    deleted.append(str(child.relative_to(args.root)))
                elif child.is_file() and child.suffix in (".png", ".import"):
                    freed += child.stat().st_size
                    child.unlink()
                    deleted.append(str(child.relative_to(args.root)))

    if clean_qa or clean_all:
        qa_dir = safe_target(args.root, "qa-evidence")
        if qa_dir.is_dir():
            for f in qa_dir.rglob("*"):
                if f.is_file():
                    freed += f.stat().st_size
            safe_rmtree(qa_dir)
            deleted.append("qa-evidence")

    if clean_all:
        pruned = prune_expired_leases(args.root)
        if pruned > 0:
            deleted.append(f".agent-state/leases.json ({pruned} expired lease(s) pruned)")
        dangling_files = find_dangling_temp_files(args.root)
        for df in dangling_files:
            try:
                freed += df.stat().st_size
                df.unlink()
                deleted.append(str(df.relative_to(args.root)))
            except (OSError, PermissionError):
                pass

    human_freed = f"{freed / (1024 * 1024):.1f} MB" if freed >= 1024 * 1024 else f"{freed / 1024:.1f} KB" if freed >= 1024 else f"{freed} bytes"
    summary = f"Cleaned {len(deleted)} capture/evidence item(s) ({human_freed} freed)" if deleted else "No ephemeral capture artifacts to clean"
    return result("clean", summary, artifacts=deleted, freed_bytes=freed, status="success")


def cmd_capture(args):
    if any(value is not None and value <= 0 for value in (getattr(args, "width", None), getattr(args, "height", None))):
        raise HarnessError("INVALID_ARGUMENT", "Capture dimensions must be positive")
    args.context.update(inspect_context(args.root, args.godot, args.timeout))
    if args.all_scenes:
        discovered = ["res://" + p.relative_to(args.root).as_posix() for p in project_files(args.root, ".tscn")]
        if not getattr(args, "include_components", False):
            filtered = [s for s in discovered if not any(c in s.lower() for c in ("/components/", "/widgets/", "_component.tscn", "/sub_nodes/"))]
            scenes = filtered if filtered else discovered
        else:
            scenes = discovered
    else:
        scenes = args.scenes or [args.scene or args.context["authored_settings"]["main_scene"]]
    batch = args.scenes is not None or args.all_scenes
    if not scenes:
        return result("capture", "No scenes found; no captures ran", status="skipped")
    scenes = list(dict.fromkeys(scenes))
    if args.output:
        output = safe_target(args.root, args.output)
        if getattr(args, "clean", False) and output.is_dir():
            safe_rmtree(output)
        output.mkdir(parents=True, exist_ok=True)
    else:
        tests_sc_dir = safe_target(args.root, "tests/screenshots")
        if tests_sc_dir.is_dir():
            for item in list(tests_sc_dir.iterdir()):
                try:
                    if item.is_dir():
                        safe_rmtree(item)
                    elif item.is_file() and item.suffix.lower() in (".png", ".import", ".json", ".log"):
                        item.unlink(missing_ok=True)
                except OSError:
                    pass
        parent = safe_target(args.root, "screenshots/debug")
        parent.mkdir(parents=True, exist_ok=True)
        if getattr(args, "clean", False):
            prune_debug_captures(args.root, purge_all=True)
        else:
            prune_debug_captures(args.root, keep=getattr(args, "keep", 5) or 5)
        output = Path(tempfile.mkdtemp(prefix="capture-", dir=parent))
    if not batch:
        return capture_scene(args, scenes[0], output)
    def run(item):
        index, scene = item
        try:
            response = capture_scene(args, scene, safe_target(args.root, output / f"{index + 1:04d}"))
        except HarnessError as exc:
            response = result("capture", str(exc), [finding(exc.code, str(exc))])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            response = result("capture", str(exc), [finding("INVALID_DATA", str(exc))])
        response["scene"] = scene
        if "capture" in response:
            response["capture"] = {key: value for key, value in response["capture"].items() if key != "nodes"}
        return response
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(scenes))) as pool:
        captures = list(pool.map(run, enumerate(scenes)))
    failures = [{**issue, "scene": capture["scene"]} for capture in captures for issue in capture["findings"]]
    report = output / "batch_results.json"
    atomic_write(report, json.dumps(captures, indent=2, sort_keys=True) + "\n")
    python = sys.executable
    if importlib.util.find_spec("PIL") is None:
        local = args.root / ".harness/venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if local.is_file():
            python = str(local)
    artifacts = [str(report)] + [path for capture in captures for path in capture["artifacts"]]
    exports = {}
    try:
        gallery = execute([python, str(TOOLS_DIR / "contact_sheet.py"), str(report)], timeout=args.timeout, log=False)
        exports = json.loads(gallery.stdout) if gallery.stdout.startswith("{") else {}
        if not isinstance(exports, dict) or not isinstance(exports.get("artifacts"), list):
            raise HarnessError("GRID_EXPORT_FAILED", exports.get("error", "Grid exporter did not return artifacts") if isinstance(exports, dict) else "Invalid grid result")
        artifacts.extend(exports["artifacts"])
        failures.extend(command_findings(gallery, "Review grid export"))
    except (HarnessError, ValueError) as exc:
        failures.append(finding("GRID_EXPORT_FAILED", str(exc)))
        # Keep any completed gallery/sheets as well as every individual capture after an export failure.
        artifacts.extend(str(p) for p in [output / "gallery.html", *sorted(output.glob("contact_sheet_*.png"))] if p.is_file())
    success = sum(capture["status"] == "success" for capture in captures)
    return result("capture", f"{success}/{len(captures)} scenes captured; inspect the review grid", failures, artifacts,
                  captures=captures, grid=exports, concurrency=min(3, len(scenes)))


def cmd_test(args):
    suites = discover_tests(args.root)
    tier = getattr(args, "tier", None)
    changed_only = getattr(args, "changed", False)

    if changed_only:
        try:
            res = execute(["git", "status", "--porcelain"], cwd=args.root, log=False)
            changed_names = [line.strip().split()[-1] for line in res.stdout.splitlines() if line.strip()]
            changed_stems = {Path(p).stem.lower() for p in changed_names}
            filtered = [s for s in suites if any(stem in s.stem.lower() for stem in changed_stems)]
            if filtered:
                suites = filtered
        except Exception:
            pass

    if tier:
        if tier in ("minor-doc", "minor-visual"):
            return result("test", f"Tier '{tier}' requires visual/doc checks, not test suite execution", status="skipped")
        elif tier == "smoke":
            suites = [s for s in suites if "smoke" in s.name.lower()] or suites[:1]
        elif tier == "sanity":
            suites = [s for s in suites if "sanity" in s.name.lower()] or suites[:2]

    if args.suite:
        selected = project_path(args.root, args.suite)
        if selected not in suites:
            raise HarnessError("INVALID_SUITE", "Select a tests/**/test_*.gd project-relative path")
        suites = [selected]
    paths = [str(p.relative_to(args.root)) for p in suites]
    if args.list or not suites:
        return result("test", "Discovered suites" if suites else "No test suites found; no tests ran",
                      status="success" if suites else "skipped", suites=paths)
    findings = []
    args.context.update(inspect_context(args.root, args.godot, args.timeout))
    strict_leaks = getattr(args, "strict_leaks", False)
    for suite in suites:
        completed = run_headless_godot(["--script", str(suite)], root=args.root,
                                      godot=args.context["engine_binary"], timeout=args.timeout)
        findings.extend(command_findings(completed, str(suite.relative_to(args.root)), strict_leaks=strict_leaks))
    return result("test", f"Ran {len(suites)} suite(s)", findings, suites=paths)


def cmd_baseline(args):
    args.context.update(inspect_context(args.root, args.godot, args.timeout))
    scene = getattr(args, "scene", None) or args.context["authored_settings"]["main_scene"]
    if not scene:
        raise HarnessError("SCENE_REQUIRED", "Project has no main scene; supply --scene")

    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', scene.replace("res://", ""))
    baseline_path = safe_target(args.root, f".harness/baselines/{clean_name}.json")

    with temp_directory(prefix="gdh-baseline-") as tmp:
        out_dir = Path(tmp)
        cap_res = capture_scene(args, scene, out_dir)
        if cap_res["status"] == "failed":
            return cap_res
        manifest_path = out_dir / "scene_manifest.json"

        diff_engine = load_tool("baseline_diff")
        if getattr(args, "save", False):
            loaded = diff_engine.save_baseline(manifest_path, baseline_path)
            return result("baseline", f"Saved baseline layout for {scene} ({len(loaded['nodes'])} nodes)",
                          artifacts=[str(baseline_path)],
                          next_command=f"python game.py baseline --check --scene {scene} --json")

        if not baseline_path.is_file():
            diff_engine.save_baseline(manifest_path, baseline_path)
            return result("baseline", f"Initialized first baseline layout for {scene}",
                          artifacts=[str(baseline_path)],
                          next_command=f"python game.py baseline --check --scene {scene} --json")

        tol = getattr(args, "tolerance", 1.0) or 1.0
        findings_data = diff_engine.diff_baselines(baseline_path, manifest_path, tolerance=tol)
        findings = [finding(f["code"], f["message"], fix_hint=f.get("fix_hint"), **{k: v for k, v in f.items() if k not in ("code", "message", "fix_hint")}) for f in findings_data]

        summary = f"Baseline check clean ({len(diff_engine.load_manifest(baseline_path)['nodes'])} nodes matched within {tol}px)" if not findings else f"Baseline check found {len(findings)} regression(s)"
        return result("baseline", summary, findings, artifacts=[str(baseline_path)], tolerance=tol)


def cmd_validate(args):
    findings = []
    engine_checked = False
    files = project_files(args.root, ".gd")
    scenes = project_files(args.root, ".tscn") + project_files(args.root, ".tres")

    # 1. UTF-8 BOM check across scripts, scenes, and resources
    for path in files + scenes:
        try:
            with path.open("rb") as f:
                header = f.read(3)
                if header == b"\xef\xbb\xbf":
                    findings.append(finding("BOM_FOUND", f"UTF-8 BOM header detected: {path.name}", file=str(path.relative_to(args.root)), line=1))
        except OSError:
            pass

    # 2. Scene-First policy on scripts (word-boundary checked)
    ui_new_re = re.compile(r"\b(Control|Button|Label|Panel|Container|TextureRect)\.new\s*\(")
    stylebox_override_re = re.compile(r"\badd_theme_stylebox_override\b")
    for path in files:
        content = load_tool("docs_updater").code_text(path.read_text(encoding="utf-8", errors="ignore"))
        for line, text in enumerate(content.splitlines(), 1):
            for match in ui_new_re.finditer(text):
                term = f"{match.group(1)}.new()"
                findings.append(finding("UI_POLICY", f"Scene-First policy: {term}", file=str(path.relative_to(args.root)), line=line))
            if stylebox_override_re.search(text):
                findings.append(finding("UI_POLICY", "Scene-First policy: add_theme_stylebox_override", file=str(path.relative_to(args.root)), line=line))

    # 3. Resource validation: path references, header formats, undeclared resources, PackedByteArray
    for path in scenes:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        rel_path = str(path.relative_to(args.root))

        first_line = next((l.strip() for l in lines if l.strip() and not l.strip().startswith(";")), "")
        if path.suffix == ".tscn" and (not first_line.startswith("[gd_scene") or "format=" not in first_line):
            findings.append(finding("FORMAT_UNSUPPORTED", "Scene missing valid [gd_scene format=3] header", file=rel_path, line=1))
        elif path.suffix == ".tres" and (not first_line.startswith("[gd_resource") or "format=" not in first_line):
            findings.append(finding("FORMAT_UNSUPPORTED", "Resource missing valid [gd_resource format=3] header", file=rel_path, line=1))

        declared_ext = set()
        declared_sub = set()
        for l in lines:
            m_ext = re.search(r'\[ext_resource\b.*?\bid="([^"]+)"', l)
            if m_ext:
                declared_ext.add(m_ext.group(1))
            m_sub = re.search(r'\[sub_resource\b.*?\bid="([^"]+)"', l)
            if m_sub:
                declared_sub.add(m_sub.group(1))

        for line_num, text in enumerate(lines, 1):
            for resource in re.findall(r'\bpath="(res://[^"\n]+)"', text):
                try:
                    project_path(args.root, resource)
                except HarnessError as exc:
                    findings.append(finding("RESOURCE_REFERENCE", str(exc), file=rel_path, line=line_num))

            for ext_ref in re.findall(r'ExtResource\("([^"]+)"\)', text):
                if ext_ref not in declared_ext:
                    findings.append(finding("UNDECLARED_RESOURCE_ID", f"ExtResource ID '{ext_ref}' used without declaration in header", file=rel_path, line=line_num))
            for sub_ref in re.findall(r'SubResource\("([^"]+)"\)', text):
                if sub_ref not in declared_sub:
                    findings.append(finding("UNDECLARED_RESOURCE_ID", f"SubResource ID '{sub_ref}' used without declaration in header", file=rel_path, line=line_num))

            if "PackedByteArray(" in text:
                inside = text[text.find("PackedByteArray(") + 16:]
                if ")" not in inside:
                    findings.append(finding("CORRUPTED_BYTE_ARRAY", "Unclosed PackedByteArray data", file=rel_path, line=line_num))

    # 4. UID verification (--uid)
    if getattr(args, "uid", False):
        declared_uids = set()
        for p in scenes:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for u in re.findall(r'\buid="(uid://[^"\n]+)"', text):
                declared_uids.add(u)
        for ufile in args.root.rglob("*.uid"):
            declared_uids.add(ufile.read_text(encoding="utf-8", errors="ignore").strip())

        for path in scenes + files:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line_num, text in enumerate(lines, 1):
                if text.strip().startswith("[ext_resource") or text.strip().startswith("[gd_scene") or text.strip().startswith("[gd_resource"):
                    continue
                for ref_uid in re.findall(r'\b(uid://[a-zA-Z0-9]+)\b', text):
                    if ref_uid not in declared_uids:
                        findings.append(finding("BROKEN_UID_REFERENCE", f"Referenced UID not found in project: {ref_uid}", file=str(path.relative_to(args.root)), line=line_num))

    # 5. Orphan asset scan (--orphans)
    if getattr(args, "orphans", False):
        asset_exts = {".png", ".webp", ".wav", ".ogg", ".tres", ".gdshader"}
        all_assets = [p for p in args.root.rglob("*") if p.suffix.lower() in asset_exts and ".harness" not in p.parts and "screenshots" not in p.parts and ".godot" not in p.parts]

        corpus_lines = []
        for p in files + scenes + [args.root / "project.godot"]:
            if p.is_file():
                corpus_lines.append(p.read_text(encoding="utf-8", errors="ignore"))
        corpus = "\n".join(corpus_lines)

        for asset in all_assets:
            rel = asset.relative_to(args.root).as_posix()
            res_ref = "res://" + rel
            if res_ref not in corpus and rel not in corpus and asset.name not in corpus:
                findings.append(finding("UNREFERENCED_RESOURCE", f"Orphaned asset file: {rel}", file=rel))

    if args.engine:
        args.context.update(inspect_context(args.root, args.godot, args.timeout))
        binary = args.context["engine_binary"]
        if not findings:
            checked = run_headless_godot(["--script", str(TOOLS_DIR / "engine_check.gd")],
                {"GAME_CHECK_FILES": json.dumps(["res://" + p.relative_to(args.root).as_posix() for p in files + scenes])},
                root=args.root, godot=binary, timeout=args.timeout)
            findings.extend(command_findings(checked, "Engine resource load"))
            if not command_findings(checked, "Engine resource load"):
                engine_json(checked)
                engine_checked = True
    return result("validate", f"Policy/reference scan of {len(files)} scripts and {len(scenes)} resources" + ("; engine parse/load checked" if args.engine else "; no engine checks requested"), findings,
                  status=None if files or scenes or args.engine else "skipped", engine_checked=engine_checked, engine_check_requested=args.engine,
                  engine_scope="Selected scripts/scenes/resources loaded with existing import metadata; no editor import or gameplay execution proof" if args.engine else None)


def cmd_assets(args):
    asset_tool = load_tool("asset_inspector")
    manifest_path = safe_target(args.root, ".harness/asset-manifest.json")
    target = getattr(args, "target", None)
    native_grid = getattr(args, "grid", 16) or 16

    if getattr(args, "process", False):
        if not target:
            raise HarnessError("INVALID_ARGUMENT", "Specify asset file to process: python game.py assets --process <file>")
        target_path = project_path(args.root, target)
        output_path = project_path(args.root, args.output) if getattr(args, "output", None) else None
        res = asset_tool.process_image(
            target_path, output_path,
            defringe=getattr(args, "defringe", False),
            crop_alpha=getattr(args, "crop_alpha", False),
            scale=getattr(args, "scale", 1) or 1
        )
        return result("assets", f"Processed asset {target}: {', '.join(res['actions']) if res['actions'] else 'saved'}",
                      artifacts=[res["output"]], details=res)

    if getattr(args, "grade", False):
        if not target:
            raise HarnessError("INVALID_ARGUMENT", "Specify asset file to grade: python game.py assets --grade <file>")
        target_path = project_path(args.root, target)
        scores = {}
        if getattr(args, "scores", None):
            try:
                scores = json.loads(args.scores)
            except Exception:
                pass
        for k in ("t1", "t2", "t3"):
            if getattr(args, k, None) is not None:
                scores[k] = getattr(args, k)
        graded = asset_tool.grade_asset(target_path.relative_to(args.root), manifest_path, scores)
        overall_score = float(graded.get("scores", {}).get("overall", 0.0))
        passed = bool(graded.get("passed")) and overall_score >= 8.5
        graded["passed"] = passed
        findings = []
        if not passed:
            findings.append(finding("ASSET_RUBRIC_BELOW_THRESHOLD", f"Asset scored {overall_score}/10.0 (below 8.5 pass threshold)", file=str(target_path.relative_to(args.root))))
        return result("assets", f"Graded {target}: overall score {overall_score}/10.0 ({'PASSED' if passed else 'NEEDS_WORK'})",
                      findings, artifacts=[str(manifest_path)], evaluation=graded)

    # Default is audit
    if target:
        target_path = project_path(args.root, target)
        audit = asset_tool.audit_image(target_path, native_grid=native_grid)
        findings = [finding(f["code"], f["message"], fix_hint=f.get("fix_hint"), file=str(target_path.relative_to(args.root))) for f in audit.get("findings", [])]
        summary = f"Asset audit clean for {target}" if not findings else f"Asset audit found {len(findings)} issue(s) for {target}"
        return result("assets", summary, findings, artifacts=[str(target_path)], audit=audit)
    else:
        audit_all = asset_tool.audit_project_assets(args.root, native_grid=native_grid)
        findings = [finding(f["code"], f["message"], fix_hint=f.get("fix_hint"), file=f.get("relative_path")) for f in audit_all.get("findings", [])]
        summary = f"Scanned {audit_all['assets_scanned']} asset(s); all clean" if not findings else f"Scanned {audit_all['assets_scanned']} asset(s); found {len(findings)} issue(s)"
        return result("assets", summary, findings, audit_summary=audit_all)


def cmd_audit(args):
    auditor = load_tool("godot_auditor")
    flags = {
        "physics": getattr(args, "physics", False),
        "exports": getattr(args, "exports", False),
        "signals": getattr(args, "signals", False),
        "perf": getattr(args, "perf", False),
        "scene_first": getattr(args, "scene_first", False)
    }
    raw_findings = auditor.audit_project(args.root, flags)
    findings = [finding(f["code"], f["message"], fix_hint=f.get("fix_hint"), file=f.get("file"), line=f.get("line")) for f in raw_findings]
    summary = "Project audit clean; no logic, physics, or performance issues found" if not findings else f"Project audit found {len(findings)} issue(s)"
    return result("audit", summary, findings, status="success" if not findings else "failed")


def cmd_saves(args):
    save_tool = load_tool("save_inspector")
    target_dir = safe_target(args.root, args.dir) if getattr(args, "dir", None) else None
    audit = save_tool.audit_saves(args.root, target_dir)
    return result("saves", f"Discovered {audit['save_count']} save file(s)",
                  artifacts=[f["file"] for f in audit["files"]], details=audit)


def cmd_syntax(args):
    if args.scan:
        target = project_path(args.root, args.scan)
        files = [target] if target.is_file() else project_files(target, ".gd")
        if not files:
            return result("syntax", "No scripts found; no migration checks ran", status="skipped")
        findings = []
        args.context.update(inspect_context(args.root, args.godot, args.timeout))
        version = re.match(r"\d+\.\d+(?:\.\d+)?", args.context["engine_version"]).group()
        inactive = []
        for path in files:
            completed = execute([sys.executable, str(DOCS_UPDATER), "scan", str(path), "--engine-version", version], timeout=args.timeout, log=False)
            data = json.loads(completed.stdout)
            if "error" in data:
                raise HarnessError("RULES_INVALID", data["error"])
            findings.extend(data.get("findings", []))
            inactive = data.get("inactive_rules", [])
            if completed.returncode and not data.get("findings"):
                findings.extend(command_findings(completed, str(path)))
        return result("syntax", f"Migration hint scan of {len(files)} scripts; not compilation", findings, inactive_rules=inactive)
    if args.query:
        command = ["query", args.query]
    elif args.learn_practice_key and args.learn_practice_desc:
        command = ["learn", "--practice-key", args.learn_practice_key, "--practice-desc", args.learn_practice_desc]
    elif args.learn_syntax_old and args.learn_syntax_new:
        command = ["learn", "--syntax-old", args.learn_syntax_old, "--syntax-new", args.learn_syntax_new]
        if args.learn_syntax_context:
            command += ["--syntax-context", args.learn_syntax_context]
        if args.verified:
            command += ["--verified"]
            for flag in ("min_version", "max_version_exclusive", "matcher", "literal", "source_url"):
                value = getattr(args, flag)
                if value is not None:
                    command += ["--" + flag.replace("_", "-"), value]
    else:
        raise HarnessError("INVALID_ARGUMENT", "Select --scan, --query, or a complete pair of learning arguments")
    completed = execute([sys.executable, str(DOCS_UPDATER), *command], timeout=args.timeout)
    return result("syntax", "Documentation tool finished", command_findings(completed, "Documentation tool"), output=json.loads(completed.stdout) if completed.stdout.startswith("{") else {})


def parse_scene_outline(path: Path, root: Path) -> dict:
    ext_resources = {}
    nodes = []
    connections = []
    current_node = None
    node_count = 0
    subresource_count = 0

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    re_ext = re.compile(r'\[ext_resource\s+type="([^"]+)"\s+(?:uid="([^"]+)"\s+)?path="([^"]+)"\s+id="([^"]+)"')
    re_sub = re.compile(r'\[sub_resource\s+type="([^"]+)"\s+id="([^"]+)"')
    re_node = re.compile(r'\[node\s+name="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+parent="([^"]+)")?')
    re_conn = re.compile(r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"')

    focus_line = 1

    for line_idx, line in enumerate(lines, start=1):
        line_str = line.strip()
        if not line_str or line_str.startswith(";"):
            continue

        m_ext = re_ext.search(line_str)
        if m_ext:
            t, uid, p, rid = m_ext.group(1), m_ext.group(2), m_ext.group(3), m_ext.group(4)
            ext_resources[rid] = {"type": t, "path": p, "uid": uid, "line": line_idx}
            continue

        if re_sub.search(line_str):
            subresource_count += 1
            if current_node:
                current_node["line_end"] = line_idx - 1
                current_node = None
            continue

        m_node = re_node.search(line_str)
        if m_node:
            if current_node:
                current_node["line_end"] = line_idx - 1
            node_count += 1
            name, ntype, parent = m_node.group(1), m_node.group(2), m_node.group(3)
            unique_name = "unique_name_in_owner=true" in line_str
            instance_match = re.search(r'instance=ExtResource\("([^"]+)"\)', line_str)
            instance_id = instance_match.group(1) if instance_match else None
            instance_path = ext_resources.get(instance_id, {}).get("path") if instance_id else None

            current_node = {
                "name": name,
                "type": ntype or ("Instance: " + str(instance_path) if instance_path else "Node"),
                "parent": parent if parent is not None else ".",
                "unique_name": f"%{name}" if unique_name else None,
                "line_start": line_idx,
                "line_end": line_idx,
                "script": None,
                "properties": {}
            }
            if focus_line == 1 and parent in (None, "."):
                focus_line = line_idx
            nodes.append(current_node)
            continue

        m_conn = re_conn.search(line_str)
        if m_conn:
            if current_node:
                current_node["line_end"] = line_idx - 1
                current_node = None
            connections.append({
                "signal": m_conn.group(1),
                "from": m_conn.group(2),
                "to": m_conn.group(3),
                "method": m_conn.group(4),
                "line": line_idx
            })
            continue

        if current_node and "=" in line_str and not line_str.startswith("["):
            current_node["line_end"] = line_idx
            k, v = line_str.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "script":
                m_scr = re.search(r'ExtResource\("([^"]+)"\)', v)
                if m_scr and m_scr.group(1) in ext_resources:
                    current_node["script"] = ext_resources[m_scr.group(1)]["path"]
            elif k in ("collision_layer", "collision_mask", "y_sort_enabled", "z_index", "position", "offset", "size", "visible", "mouse_filter"):
                current_node["properties"][k] = v
            elif not v.startswith("PackedByteArray") and not v.startswith("Array") and len(v) < 80:
                current_node["properties"][k] = v

    if current_node:
        current_node["line_end"] = len(lines)

    compact_nodes = []
    for n in nodes:
        node_repr = {
            "path": (n["parent"] + "/" + n["name"]) if n["parent"] != "." else n["name"],
            "type": n["type"],
            "lines": [n["line_start"], n["line_end"]]
        }
        if n["unique_name"]:
            node_repr["unique_name"] = n["unique_name"]
        if n["script"]:
            node_repr["script"] = n["script"]
        if n["properties"]:
            node_repr["properties"] = n["properties"]
        compact_nodes.append(node_repr)

    rel_scene = str(path.relative_to(root)).replace("\\", "/") if path.is_relative_to(root) else path.name

    return {
        "scene": rel_scene,
        "node_count": node_count,
        "subresource_count": subresource_count,
        "connection_count": len(connections),
        "ext_resources": list(ext_resources.values()),
        "nodes": compact_nodes,
        "connections": connections,
        "focus_line": focus_line
    }


def cmd_scene_outline(args):
    target = getattr(args, "opt_scene", None) or getattr(args, "scene", None)
    if not target:
        raise HarnessError("INVALID_ARGUMENT", "Specify a scene path (positional or --scene)")
    clean_target = target.replace("res://", "")
    scene_path = safe_target(args.root, clean_target)
    if not scene_path.is_file():
        raise HarnessError("SCENE_NOT_FOUND", f"Scene not found: {target}")

    outline = parse_scene_outline(scene_path, args.root)
    return result("scene-outline", f"Outline for {target}: {outline['node_count']} nodes, {outline['connection_count']} connections",
                  artifacts=[str(scene_path)], outline=outline,
                  next_command=f"view_file line range [{outline.get('focus_line', 1)}, {min(len(outline.get('nodes', []))*10 + 20, 100)}] or edit target nodes")


_TRIVIAL_CHAT_PHRASES = {
    "", "hi", "hello", "hey", "hiya", "yo", "sup", "greetings",
    "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening", "good night",
    "how are you", "whats up", "what is up",
    "ok", "okay", "k", "kk", "yep", "yup", "yeah", "yes", "no", "nope", "nah",
    "thanks", "thank you", "thx", "ty", "thanks a lot", "thank you very much",
    "ok thanks", "okay thanks", "cool", "nice", "great", "awesome", "good",
    "got it", "understood", "makes sense", "sounds good", "all good",
    "continue", "go", "go ahead", "proceed", "carry on", "please continue", "next",
    "never mind", "nevermind", "bye", "goodbye", "see ya",
}

_TRIVIAL_CHAT_WORDS = {
    "hi", "hello", "hey", "hiya", "yo", "ok", "okay", "yes", "yeah", "yep",
    "yup", "no", "nope", "nah", "thanks", "thank", "you", "thx", "ty",
    "please", "continue", "go", "ahead", "proceed", "cool", "nice", "great",
    "good", "morning", "afternoon", "evening", "there", "got", "it",
    "sounds", "fine", "sure", "alright", "bye",
}

_PLAYBOOK_STOPWORDS = {
    "the", "a", "an", "is", "in", "to", "for", "and", "or", "of", "with", "at",
    "by", "from", "up", "about", "into", "over", "after", "it", "this", "that",
    "these", "those", "all", "each", "every", "some", "any", "no", "not", "only",
    "game", "godot", "when", "using", "used", "make", "building", "expert", "patterns",
    "systems", "system", "tools", "data", "code", "files", "file", "which", "their",
    "other", "more", "also", "such", "than", "will", "would", "could", "should",
    "mastery", "advanced", "essentials", "pattern", "foundations", "guide", "skill",
}

_PLAYBOOK_TRIGGER_MAP = {
    "2d-essentials": ["tilemap", "tilemaplayer", "parallax", "canvaslayer", "gpuparticles2d", "cpuparticles2d", "2d light"],
    "godot-2d-animation": ["animatedsprite2d", "spriteframes", "cutout animation", "skeletal 2d", "bone2d", "squash and stretch"],
    "godot-2d-physics": ["2d physics", "collisionshape2d", "collisionpolygon2d", "collision_layer", "collision_mask", "area2d", "raycast2d", "move_and_collide"],
    "godot-animation-player": ["animationplayer", "track_insert_key", "reset track", "blend_times"],
    "godot-audio-systems": ["audiostreamplayer", "audiostreamplayer2d", "audiobus", "audioserver", "music crossfade", "sfx", "bgm"],
    "godot-autoload-architecture": ["autoload", "autoloads", "singleton", "singletons", "gamemanager", "eventbus", "signal_bus"],
    "godot-camera-systems": ["camera2d", "camera3d", "springarm3d", "camera shake", "trauma system", "camera_limits"],
    "godot-characterbody-2d": ["characterbody2d", "move_and_slide", "is_on_floor", "coyote time", "jump buffer", "velocity"],
    "godot-composition": ["entity-component", "entity component", "ecs", "hitbox", "hurtbox", "composition pattern"],
    "godot-dialogue-system": ["dialogueline", "dialoguechoice", "dialoguegraph", "typewriter", "branching dialogue", "dialogue", "npc conversation"],
    "godot-economy-system": ["economy", "currency", "shop_item", "loot_table", "loot table", "merchant", "gold", "wallet"],
    "godot-gdscript-mastery": ["gdscript", "static typing", "unique_nodes", "@onready", "class_name", "signal up", "call down", "callable"],
    "godot-input-handling": ["inputmap", "inputevent", "gamepad", "controller", "rebinding", "deadzone", "input buffer", "keybind"],
    "godot-inventory-system": ["inventory", "equipment", "max_stack", "drag and drop", "chest inventory", "grid inventory"],
    "godot-multiplayer-networking": ["multiplayer", "rpc", "enetmultiplayerpeer", "multiplayersynchronizer", "multiplayerspawner", "authority", "client prediction", "rollback", "desync", "enet"],
    "godot-quest-system": ["quest", "quests", "objectives", "questobjective", "quest chain", "quest rewards"],
    "godot-resource-data-patterns": ["refcounted", "itemdata", "characterstats", "custom resource", "@export resource", "typed arrays"],
    "godot-save-load-systems": ["save system", "savesystem", "user://", "fileaccess", "save profile", "slot save", "save migration", "persistence"],
    "godot-scene-management": ["scene loading", "scene transition", "async loading", "resourceloader", "change_scene", "packedscene", "loading screen"],
    "godot-signal-architecture": ["signal", "signals", "signal up call down", "event bus", "event_bus", "typed signals"],
    "godot-state-machine-advanced": ["state machine", "hsm", "hierarchical state machine", "pushdown automata", "fsm"],
    "godot-testing-patterns": ["gdunit4", "headless ci", "snapshot test", "scene integration test", "tdd", "unit test", "test suite"],
    "godot-tilemap-mastery": ["tilemaplayer", "tileset", "autotiling", "custom data layer", "destructible tiles", "tilemap"],
    "godot-tweening": ["tween", "tweening", "create_tween", "tween_property", "tween_callback", "easing"],
    "godot-ui-containers": ["container", "hboxcontainer", "vboxcontainer", "gridcontainer", "margincontainer", "scrollcontainer", "anchors", "responsive ui"],
    "godot-ui-theming": ["theme", "stylebox", "styleboxflat", "styleboxtexture", "custom font", "theme resource"],
    "ui-mockup-pipeline": ["mockup", "mockup-dissect", "mockup-grade", "bezel", "9-patch", "nine-patch", "styleboxtexture", "styleboxflat", "hud", "ui panel"],
    "core-architecture": ["autoload", "scene-first", "inspector-first", "y-sort", "ysort", "singleton"],
    "godot-test-qa": ["baseline", "capture", "validate", "proportionate", "regression", "visual qa"],
    "gdscript-migration": ["godot 4", "syntax scan", "static typing", "migration", "scene-outline"],
    "agent-coordination": ["agent_lock", "agent lock", "lease", "leases", "write-off", "journal.jsonl", "multi-agent", "swarm"],
    "token-budget": ["token budget", "context compression", "ctx_hash", "ctx_stale", "project_state.json"],
}


def _has_word_kw(text: str, keywords) -> bool:
    for kw in keywords:
        kw_clean = kw.strip().lower()
        if not kw_clean:
            continue
        start_b = r"\b" if (kw_clean[0].isalnum() or kw_clean[0] == "_") else r"(?<!\w)"
        end_b = r"\b" if (kw_clean[-1].isalnum() or kw_clean[-1] == "_") else ""
        if re.search(start_b + re.escape(kw_clean) + end_b, text):
            return True
    return False


def _is_trivial_prompt(task_desc: str, extracted_files: list) -> bool:
    if extracted_files:
        return False
    raw = (task_desc or "").strip()
    if not raw or not any(ch.isalpha() for ch in raw):
        return True
    lower = raw.lower()
    clean_alpha = re.sub(r"[^\w\s]", "", lower).strip()
    if clean_alpha in _TRIVIAL_CHAT_PHRASES:
        return True
    if "?" in raw or any(sym in raw for sym in ("_", "/", "\\", "(", ")")):
        return False
    words = clean_alpha.split()
    return 0 < len(words) <= 4 and all(w in _TRIVIAL_CHAT_WORDS for w in words)


def _check_project_art_style(root: Path) -> dict:
    art_style = ""
    state_file = root / ".context" / "project_state.json"
    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            val = data.get("art_style_direction") or data.get("art_style") or data.get("context", {}).get("art_style_direction") or ""
            if isinstance(val, str) and val.strip() and val.strip().lower() not in ("unset", "none", "tbd", "null"):
                art_style = val.strip()
        except Exception:
            pass
    style_guide = root / "docs" / "art" / "style_guide.md"
    style_guide_exists = False
    if style_guide.is_file():
        try:
            if style_guide.read_text(encoding="utf-8", errors="ignore").strip():
                style_guide_exists = True
                if not art_style:
                    art_style = "docs/art/style_guide.md"
        except OSError:
            pass
    defined = bool(art_style or style_guide_exists)
    return {
        "art_style_direction": art_style,
        "defined": defined,
        "style_guide_exists": style_guide_exists,
    }


def _scan_matched_playbooks(root: Path, corpus_text: str) -> list:
    matched = []
    seen = set()
    search_bases = [
        (root / ".agents" / "playbooks", ".agents/playbooks"),
        (root / ".agents" / "skills", ".agents/skills"),
    ]
    for base_dir, rel_prefix in search_bases:
        if not base_dir.is_dir():
            continue
        for skill_dir in sorted(base_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            name = skill_dir.name
            rel_path = f"{rel_prefix}/{name}/SKILL.md"
            if rel_path in seen:
                continue
            triggers = list(_PLAYBOOK_TRIGGER_MAP.get(name, []))
            triggers.append(name)
            clean_name = name.removeprefix("godot-").replace("-", " ")
            if len(clean_name) >= 4 and clean_name not in _PLAYBOOK_STOPWORDS:
                triggers.append(clean_name)
            for part in clean_name.split():
                if len(part) >= 5 and part not in _PLAYBOOK_STOPWORDS:
                    triggers.append(part)
            try:
                content = skill_md.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"^---\s*(.*?)\s*---", content, re.DOTALL | re.MULTILINE)
                if m:
                    for line in m.group(1).splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                            for w in re.findall(r"\b[a-zA-Z_]{6,}\b", desc.lower()):
                                if w not in _PLAYBOOK_STOPWORDS:
                                    triggers.append(w)
            except Exception:
                pass
            if _has_word_kw(corpus_text, triggers):
                seen.add(rel_path)
                matched.append(rel_path)
    return matched


def cmd_plan_task(args):
    task_desc = getattr(args, "opt_task", None) or getattr(args, "task_desc", "") or ""
    files = list(getattr(args, "files", []) or [])

    writing_heavy_keywords = (
        "plan", "implementation_plan", "gdd", "doc", "docs", "documentation",
        "readme", "dialogue", "dialog", "story", "lore", "quest text",
        "explain", "walkthrough", "copywriting", "tutorial text", "writing",
    )
    low_writing_keywords = (
        "fix", "bug", "issue", "error", "crash", "collision", "offset",
        "button", "export", "shader", "particle", "physics", "test",
        "capture", "refactor", "clean", "baseline", "syntax", "audit",
        "mockup", "dissect", "grade", "stylebox", "bezel",
    )

    lower_task = task_desc.lower()
    is_writing_heavy = _has_word_kw(lower_task, writing_heavy_keywords)
    has_low_writing = _has_word_kw(lower_task, low_writing_keywords)

    if is_writing_heavy and not (has_low_writing and ("fix" in lower_task or "bug" in lower_task)):
        caveman_mode = "off"
        caveman_reason = "Writing-heavy task detected (documentation, plan, lore, dialogue, or explanation requested); normal prose required for full clarity."
    else:
        caveman_mode = "full"
        caveman_reason = "Low-writing coding, debugging, or verification task detected; Caveman mode enabled to conserve output & context tokens."

    extracted_files = list(files)
    file_matches = re.findall(r'[\w./\\-]+\.(?:tscn|gd|tres|md|json|gdshader|txt|png|webp)', task_desc)
    for fm in file_matches:
        if fm not in extracted_files:
            extracted_files.append(fm)

    major_keywords = (
        "autoload", "autoloads", "architecture", "rewrite", "overhaul", "migration",
        "multiplayer", "state machine", "core refactor", "system rewrite", "upgrade engine",
    )
    ui_mockup_keywords = (
        "mockup", "mockup-dissect", "mockup-grade", "hud", "ui", "stylebox",
        "styleboxtexture", "styleboxflat", "9-patch", "nine-patch", "bezel",
        "modal", "menu", "hotbar", "button", "panel", "theme", "dialogue box", "dialog box",
    )
    asset_keywords = (
        "asset", "assets", "sprite", "sprites", "texture", "icon", "icons",
        "defringe", "crop-alpha", "canva", "palette", "pixel art", "crest", "backdrop",
    )
    multi_agent_keywords = (
        "swarm", "multi-agent", "multi agent", "parallel", "concurrent",
        "subagent", "subagents", "cavecrew", "lease", "leases", "agent_lock", "write-off",
    )
    qa_keywords = (
        "test", "tests", "qa", "verify", "validate", "audit", "baseline", "capture", "regression", "smoke",
    )
    migration_keywords = (
        "godot 4", "4.x", "syntax", "static typing", "typed gdscript", "migrate",
    )
    edit_action_verbs = (
        "fix", "edit", "add", "create", "update", "implement", "write", "remove",
        "delete", "change", "modify", "build", "make", "patch", "wire", "adjust",
        "polish", "test", "run", "verify", "audit", "capture", "render", "generate",
        "refactor", "migrate", "rewrite", "overhaul", "clean", "tune", "optimize",
        "debug", "design", "dissect", "grade",
    )
    question_starters = (
        "what is", "what's", "whats", "what are", "what does", "where is", "where are",
        "which ", "who is", "when ", "how many", "how much", "how do i", "how does",
        "is ", "are ", "does ", "do ", "can ",
    )

    is_major = _has_word_kw(lower_task, major_keywords) or len(extracted_files) > 2
    has_ui_kw = _has_word_kw(lower_task, ui_mockup_keywords) or any(
        f.endswith(".tscn") and any(tok in f.lower() for tok in ("ui", "hud", "menu", "modal", "dialog", "hotbar", "panel"))
        for f in extracted_files
    )
    has_asset_kw = _has_word_kw(lower_task, asset_keywords) or any(
        f.endswith((".png", ".webp")) for f in extracted_files
    )
    is_trivial = _is_trivial_prompt(task_desc, extracted_files)
    is_question = (
        not is_trivial
        and not is_major
        and (lower_task.strip().startswith(question_starters) or task_desc.strip().endswith("?"))
        and not _has_word_kw(lower_task, edit_action_verbs)
        and len(extracted_files) <= 1
    )

    # Task type classification
    if is_trivial:
        task_type = "chat"
    elif is_question:
        task_type = "question"
    elif has_ui_kw:
        task_type = "ui"
    elif has_asset_kw:
        task_type = "assets"
    elif _has_word_kw(lower_task, multi_agent_keywords):
        task_type = "multi_agent"
    elif _has_word_kw(lower_task, migration_keywords) and not is_major:
        task_type = "migration"
    elif _has_word_kw(lower_task, qa_keywords) and not any(f.endswith((".tscn", ".gd")) for f in extracted_files):
        task_type = "qa"
    elif (all(f.endswith((".md", ".txt")) for f in extracted_files) and extracted_files) or (is_writing_heavy and not has_low_writing and not extracted_files):
        task_type = "docs"
    elif is_major or any(f.endswith(".tscn") for f in extracted_files):
        task_type = "architecture"
    else:
        task_type = "logic"

    # Tier, change_class, and triage_category classification
    if is_trivial:
        triage_category = "trivial_chat"
        tier = "minor-doc"
        change_class = "Minor"
        verification_commands = ["python game.py clean --audit --json --compact"]
    elif is_question:
        triage_category = "quick_question"
        tier = "minor-doc"
        change_class = "Minor"
        verification_commands = ["python game.py clean --audit --json --compact"]
    elif all(f.endswith(".md") or f.endswith(".txt") for f in extracted_files) and extracted_files:
        triage_category = "minor_doc"
        tier = "minor-doc"
        change_class = "Minor"
        verification_commands = ["python game.py clean --audit --json"]
    elif not is_major and (has_ui_kw or any(f.endswith(".tscn") for f in extracted_files) or has_asset_kw):
        triage_category = "ui_mockup" if has_ui_kw else "minor_visual"
        tier = "minor-visual"
        change_class = "Minor"
        first_tscn = next((f for f in extracted_files if f.endswith(".tscn")), "")
        if triage_category == "ui_mockup":
            verification_commands = [
                f"python game.py mockup-dissect --scene {first_tscn} --json --compact" if first_tscn else "python game.py mockup-dissect --check-prereqs --json --compact",
                "python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact",
                f"python game.py capture --scene {first_tscn} --json" if first_tscn else "python game.py capture --json",
            ]
        else:
            verification_commands = [
                f"python game.py syntax --scan {first_tscn} --json" if first_tscn else "python game.py syntax --scan . --json",
                "python game.py baseline --check --json",
                f"python game.py capture --scene {first_tscn} --json" if first_tscn else "python game.py capture --json",
            ]
    elif not is_major and task_type == "docs":
        triage_category = "minor_doc"
        tier = "minor-doc"
        change_class = "Minor"
        verification_commands = ["python game.py clean --audit --json"]
    elif not is_major:
        triage_category = "minor_logic"
        tier = "minor-logic"
        change_class = "Minor"
        verification_commands = [
            "python game.py syntax --scan . --json",
            "python game.py test --changed --json",
        ]
    else:
        triage_category = "major"
        tier = "major"
        change_class = "Major"
        verification_commands = [
            "python game.py syntax --scan . --json",
            "python game.py test --json",
            "python game.py capture --all-scenes --json",
            "python game.py validate --engine --json",
        ]

    skip_graphify = change_class != "Major"
    lock_required = bool(
        getattr(args, "multi_agent", False)
        or _has_word_kw(lower_task, multi_agent_keywords)
    )

    # Required core skills in .agents/skills/<skill>/SKILL.md
    required_skills = []
    if triage_category not in ("trivial_chat", "quick_question"):
        if task_type in ("ui", "assets") or triage_category in ("ui_mockup", "minor_visual"):
            required_skills.append(".agents/skills/ui-mockup-pipeline/SKILL.md")
        if is_major or task_type == "architecture" or any(f.endswith((".tscn", ".tres")) for f in extracted_files) or _has_word_kw(lower_task, ("scene", "node", "autoload", "autoloads", "singleton", "architecture", "export", "y-sort", "ysort", "signal", "refactor", "rewrite", "overhaul")):
            required_skills.append(".agents/skills/core-architecture/SKILL.md")
        if task_type in ("logic", "migration") or triage_category == "minor_logic" or is_major or any(f.endswith(".gd") for f in extracted_files) or _has_word_kw(lower_task, ("gdscript", "script", "syntax", "migration", "migrate", "typing", "typed", "bug", "fix", "error", "crash", "collision", "physics")):
            required_skills.append(".agents/skills/gdscript-migration/SKILL.md")
        if task_type == "qa" or is_major or _has_word_kw(lower_task, qa_keywords):
            required_skills.append(".agents/skills/godot-test-qa/SKILL.md")
        if lock_required or task_type == "multi_agent":
            required_skills.append(".agents/skills/agent-coordination/SKILL.md")
        if is_major or _has_word_kw(lower_task, ("token", "tokens", "budget", "compact", "context", "cache", "checkpoint")):
            required_skills.append(".agents/skills/token-budget/SKILL.md")
        if not required_skills:
            required_skills.append(".agents/skills/core-architecture/SKILL.md")

    corpus_text = f"{lower_task} {' '.join(extracted_files).lower()}"
    matched_playbooks = _scan_matched_playbooks(args.root, corpus_text) if triage_category != "trivial_chat" else []

    # Art style gate check for UI / art / mockup / visual tasks
    style_status = _check_project_art_style(args.root)
    needs_art_style = (
        task_type in ("ui", "assets")
        or triage_category in ("ui_mockup", "minor_visual")
    )
    ask_user_art_style = bool(needs_art_style and not style_status["defined"])
    art_style_instruction = (
        "ART_STYLE_DIRECTION_UNSET: Explicitly ask the user to decide and define their art & UI style direction before creating mockups or UI assets"
        if ask_user_art_style
        else None
    )
    art_style_check = {
        "art_style_direction": style_status["art_style_direction"],
        "ask_user_art_style": ask_user_art_style,
        "defined": style_status["defined"],
        "instruction": art_style_instruction,
        "style_guide_exists": style_status["style_guide_exists"],
    }
    plan_findings = []
    if ask_user_art_style:
        plan_findings.append(finding(
            "ART_STYLE_DIRECTION_UNSET",
            art_style_instruction,
            fix_hint="Ask the user to choose their art & UI style direction and record it in .context/project_state.json (art_style_direction) or docs/art/style_guide.md.",
        ))

    graph_neighbors = []
    graph_file = safe_target(args.root, "graphify-out/graph.json")
    if not skip_graphify and graph_file.is_file() and extracted_files:
        try:
            gdata = json.loads(graph_file.read_text(encoding="utf-8"))
            links = gdata.get("links", [])
            for ef in extracted_files:
                norm_ef = ef.replace("\\", "/").replace("res://", "")
                for link in links:
                    s = str(link.get("source", ""))
                    t = str(link.get("target", ""))
                    if norm_ef in s and t not in graph_neighbors:
                        graph_neighbors.append(t)
                    elif norm_ef in t and s not in graph_neighbors:
                        graph_neighbors.append(s)
        except Exception:
            pass

    first_target = extracted_files[0] if extracted_files else "target file"
    skill_step = f"Read required skills: {', '.join(required_skills)}" if required_skills else "Inspect project context"
    steps = [
        f"0. {skill_step}" + (f" ({art_style_instruction})" if art_style_instruction else ""),
        f"1. Inspect target scenes/files: {f'python game.py scene-outline {first_target} --json' if first_target.endswith('.tscn') else f'view {first_target}'}",
        f"2. Execute surgical edit adhering to scene-first & @export contracts (Caveman: {caveman_mode})",
        f"3. Run proportionate verification: {verification_commands[0]}",
        "4. Refresh context and persist checkpoint: python game.py context --refresh --json",
    ]

    first_next = f"python game.py scene-outline {first_target} --json" if first_target.endswith(".tscn") else verification_commands[0]

    return result(
        "plan-task",
        f"Task classified as {change_class} ({tier}, triage={triage_category}); Caveman mode: {caveman_mode}",
        findings=plan_findings,
        status="success",
        next_command=first_next,
        task=task_desc,
        task_type=task_type,
        triage_category=triage_category,
        change_class=change_class,
        tier=tier,
        caveman_mode=caveman_mode,
        caveman_reason=caveman_reason,
        required_skills=required_skills,
        matched_playbooks=matched_playbooks,
        skip_graphify=skip_graphify,
        lock_required=lock_required,
        art_style_check=art_style_check,
        ask_user_art_style=ask_user_art_style,
        affected_files=extracted_files,
        graph_neighbors=graph_neighbors[:5],
        verification_commands=verification_commands,
        Verification_plan=verification_commands,
        verification_plan=verification_commands,
        suggested_commands=verification_commands,
        steps=steps,
    )


def _load_ui_pipeline_module(name, root=None):
    candidates = []
    if root is not None:
        candidates.append(Path(root) / "core" / "tools" / "ui_pipeline" / f"{name}.py")
        candidates.append(Path(root) / "tools" / "ui_pipeline" / f"{name}.py")
    candidates.append(TOOLS_DIR / "ui_pipeline" / f"{name}.py")
    candidates.append(PROJECT_ROOT / "core" / "tools" / "ui_pipeline" / f"{name}.py")
    candidates.append(PROJECT_ROOT / "tools" / "ui_pipeline" / f"{name}.py")
    mod_path = next((c for c in candidates if c.is_file()), TOOLS_DIR / "ui_pipeline" / f"{name}.py")
    if not mod_path.is_file():
        raise HarnessError("TOOL_UNAVAILABLE", f"UI pipeline module not found: {name}.py")
    parent_str = str(mod_path.parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)
    spec = importlib.util.spec_from_file_location(f"ui_pipeline_{name}", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_mockup_dissect(args):
    dissect_mod = _load_ui_pipeline_module("mockup_dissect", args.root)
    if getattr(args, "check_prereqs", False):
        prereqs = dissect_mod.check_prerequisites(
            args.root,
            scene=getattr(args, "scene", None),
            mockup=getattr(args, "mockup", None),
        )
        raw_findings = prereqs.get("findings", [])
        findings = [
            finding(
                f.get("code", "PREREQ_CHECK"),
                f.get("message", ""),
                fix_hint=f.get("fix_hint"),
                file=f.get("file"),
                severity=f.get("severity", "warning"),
            )
            for f in raw_findings
        ]
        ok = bool(prereqs.get("ok", True))
        scene_rel = prereqs.get("scene", "modals/game_ui.tscn")
        summary = (
            f"UI pipeline prerequisites verified for {scene_rel}"
            if ok
            else f"UI pipeline prerequisite check failed for {scene_rel}"
        )
        next_cmd = (
            f"python game.py mockup-dissect --scene {scene_rel} --json --compact"
            if ok
            else f"Fix prerequisite findings and run python game.py mockup-dissect --check-prereqs --json --compact"
        )
        return result(
            "mockup-dissect",
            summary,
            findings=findings,
            status="success" if ok else "failed",
            next_command=next_cmd,
            prerequisites=prereqs,
            art_style_configured=prereqs.get("art_style_configured", False),
            art_style_direction=prereqs.get("art_style_direction", ""),
            ask_user_art_style=prereqs.get("ask_user_art_style", True),
            pillow_available=prereqs.get("pillow_available", False),
            scene=scene_rel,
            scene_exists=prereqs.get("scene_exists", False),
            ok=ok,
            passed=ok,
        )

    res = dissect_mod.dissect_ui(
        args.root,
        scene=getattr(args, "scene", None),
        mockup=getattr(args, "mockup", None),
        out_dir=getattr(args, "out_dir", "artifacts/ui_pipeline"),
        godot=args.godot,
        timeout=args.timeout,
    )
    m = res["manifest"]
    prereqs = res.get("prerequisites") or m.get("prerequisites", {})
    raw_findings = prereqs.get("findings", [])
    findings = [
        finding(
            f.get("code", "PREREQ_CHECK"),
            f.get("message", ""),
            fix_hint=f.get("fix_hint"),
            file=f.get("file"),
            severity=f.get("severity", "advisory"),
        )
        for f in raw_findings
    ]
    pipeline_conn = res.get("pipeline_connection") or m.get("pipeline_connection", {})
    next_cmd = pipeline_conn.get(
        "next_command",
        "python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact",
    )
    return result(
        "mockup-dissect",
        f"Dissected {m['control_count']} controls ({m.get('styled_control_count', 0)} styled) via {m['probe_mode']} (required_patch={m['measured_layers_px']['required_patch_margin_px']}px)",
        findings=findings,
        artifacts=[res["dissection_manifest"], res["handoff_manifest"]],
        status="success",
        next_command=next_cmd,
        scene=m.get("scene"),
        probe_mode=m["probe_mode"],
        measured_layers_px=m["measured_layers_px"],
        control_count=m["control_count"],
        styled_control_count=m.get("styled_control_count", 0),
        styled_controls=m.get("styled_controls", []),
        dissection_manifest=res["dissection_manifest"],
        handoff_manifest=res["handoff_manifest"],
        pipeline_connection=pipeline_conn,
        prerequisites=prereqs,
        ask_user_art_style=prereqs.get("ask_user_art_style", False),
    )


def cmd_mockup_grade(args):
    grade_mod = _load_ui_pipeline_module("mockup_grade", args.root)
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = args.root / manifest_path
    report = grade_mod.grade_dissection(manifest_path, tolerance_px=args.tolerance)
    findings = [
        finding(
            item.get("rule", "UI_GRADE_FAILED"),
            item.get("fix") or item.get("message") or str(item),
            file=item.get("node_path") or item.get("component"),
        )
        for item in report.get("failed_components", [])
    ]
    summary = (
        "UI mockup grade passed 100%"
        if report["passed"]
        else f"UI mockup grade failed: {report['failed_count']} component check(s)"
    )
    return result(
        "mockup-grade",
        summary,
        findings=findings,
        artifacts=[manifest_path.as_posix()],
        status="success" if report["passed"] else "failed",
        next_command=report.get("next_command"),
        scene=report.get("scene"),
        passed=report["passed"],
        probe_mode=report.get("probe_mode"),
        required_patch_margin_px=report.get("required_patch_margin_px"),
        graded_control_count=report.get("graded_control_count", 0),
        failed_count=report["failed_count"],
        failed_components=report["failed_components"],
        pipeline_connection=report.get("pipeline_connection"),
    )


def cmd_lock(args):
    lock_mod = load_tool("agent_lock", args.root)
    action = getattr(args, "lock_action", None) or "status"
    paths = list(getattr(args, "paths", None) or [])
    agent_id = getattr(args, "agent", "") or ""
    task_id = getattr(args, "task", "") or ""
    ttl = float(getattr(args, "ttl", 300) if getattr(args, "ttl", None) is not None else 300)
    summary_text = getattr(args, "summary", "") or ""
    force = bool(getattr(args, "force", False))
    limit = int(getattr(args, "limit", 10) or 10)

    if action in ("acquire", "write-off", "check") and not paths:
        raise HarnessError("INVALID_ARGUMENT", f"Specify target file path(s) for 'game.py lock {action}'")
    if action in ("acquire", "write-off") and not agent_id:
        raise HarnessError("INVALID_ARGUMENT", f"Specify --agent for 'game.py lock {action}'")
    if action == "write-off" and not summary_text:
        raise HarnessError("INVALID_ARGUMENT", "Specify --summary for 'game.py lock write-off'")

    lock_argv = ["--root", str(args.root), "--json", action]
    if action == "acquire":
        lock_argv.extend(paths)
        lock_argv.extend(["--agent", agent_id, "--task", task_id, "--ttl", str(ttl)])
        if summary_text:
            lock_argv.extend(["--summary", summary_text])
        if force:
            lock_argv.append("--force")
    elif action == "release":
        lock_argv.extend(paths)
        if agent_id:
            lock_argv.extend(["--agent", agent_id])
        if task_id:
            lock_argv.extend(["--task", task_id])
        if force:
            lock_argv.append("--force")
    elif action == "write-off":
        lock_argv.extend(paths)
        lock_argv.extend(["--agent", agent_id, "--summary", summary_text, "--task", task_id])
    elif action == "check":
        lock_argv.extend(paths)
    elif action == "status":
        lock_argv.extend(["--limit", str(limit)])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = lock_mod.main(lock_argv)
    raw_out = buf.getvalue().strip()
    payload = json.loads(raw_out) if raw_out.startswith("{") else {}

    findings = []
    status = "success" if rc == 0 else "failed"
    if action == "acquire":
        if rc != 0 or payload.get("status") == "conflict":
            status = "failed"
            for c in payload.get("conflicts", []):
                findings.append(finding(
                    "LOCK_CONFLICT",
                    f"Lease conflict on {c.get('file')}: held by '{c.get('owner')}' (remaining TTL: {c.get('remaining_ttl')}s)",
                    file=c.get("file"),
                ))
            summary = f"Lock conflict on {len(payload.get('conflicts', []))} file(s) for agent '{agent_id}'"
        else:
            acq = payload.get("acquired", [])
            pre = payload.get("preempted", [])
            summary = f"Acquired {len(acq)} lease(s) for agent '{agent_id}'" + (f" (preempted {len(pre)})" if pre else "")
    elif action == "release":
        rel = payload.get("released", [])
        summary = f"Released {len(rel)} lease(s)"
    elif action == "write-off":
        files_wo = payload.get("files", [])
        summary = f"Wrote off {len(files_wo)} file(s) with SHA-256 journal entry for '{agent_id}'"
    elif action == "check":
        locked_list = payload.get("locked", [])
        if rc != 0 or locked_list:
            status = "failed"
            for item in locked_list:
                findings.append(finding(
                    "FILE_LOCKED",
                    f"File {item.get('file')} is locked by '{item.get('owner')}' (remaining TTL: {item.get('remaining_ttl')}s)",
                    file=item.get("file"),
                ))
            summary = f"{len(locked_list)} path(s) currently locked"
        else:
            summary = f"All {len(payload.get('checked', []))} path(s) unlocked"
    elif action == "status":
        summary = f"{payload.get('active_count', 0)} active lease(s)"
    elif action == "prune":
        summary = f"Pruned {payload.get('pruned_count', 0)} expired lease(s); {payload.get('remaining_count', 0)} active"
    else:
        summary = f"Lock {action} completed"

    extra_fields = {k: v for k, v in payload.items() if k not in ("status", "summary")}
    extra_fields["action"] = action
    extra_fields["lock_status"] = payload.get("status", status)
    if action == "write-off" and "summary" in payload:
        extra_fields["write_off_summary"] = payload["summary"]

    artifacts = []
    leases_file = args.root / ".agent-state" / "leases.json"
    journal_file = args.root / ".agent-state" / "journal.jsonl"
    if leases_file.is_file():
        artifacts.append(str(leases_file))
    if action in ("write-off", "acquire", "release", "status") and journal_file.is_file():
        artifacts.append(str(journal_file))

    return result(
        "lock",
        summary,
        findings=findings,
        artifacts=artifacts,
        status=status,
        **extra_fields,
    )


def build_parser():
    common = Parser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS, help="Godot project directory")
    common.add_argument("--godot", default=argparse.SUPPRESS, help="Explicit Godot executable")
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS, help="Per subprocess timeout in seconds (default 30)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Emit one structured JSON result")
    common.add_argument("--compact", action="store_true", default=argparse.SUPPRESS, help="Emit ultra-dense JSON summarizing long arrays")
    common.add_argument("--out", default=argparse.SUPPRESS, help="Write UTF-8 JSON output directly to file with POSIX paths")
    common.add_argument("--full", action="store_true", default=argparse.SUPPRESS, help="Include full context block even with --compact")
    parser = Parser(description=__doc__, parents=[common])
    parser.set_defaults(command="info", handler=cmd_info)
    sub = parser.add_subparsers(dest="command")
    commands = {}
    for name, callback, help_text in (
        ("info", cmd_info, "Inspect environment and available tools"),
        ("plan-task", cmd_plan_task, "Deterministic workhorse model task planner and change classifier"),
        ("scene-outline", cmd_scene_outline, "Compact node, script, property, and signal outline for .tscn scenes"),
        ("mockup-dissect", cmd_mockup_dissect, "Slice mockup PNG + probe Control bounds into dissection_manifest.json"),
        ("mockup-grade", cmd_mockup_grade, "Deterministically grade dissection_manifest.json for StyleBox & layout rules"),
        ("capture", cmd_capture, "Render a scene and inspect its layout"),
        ("baseline", cmd_baseline, "Save or check headless UI layout baselines for visual regression testing"),
        ("test", cmd_test, "Discover and run recursive SceneTree test suites"),
        ("validate", cmd_validate, "Scan policy/references; --engine also parses/loads resources using existing imports"),
        ("assets", cmd_assets, "Audit sprite alpha, detect fringes, rescale, and grade 3-tier aesthetic rubric"),
        ("audit", cmd_audit, "Deep in-game logic, collision matrix, Y-sort, signal wiring, and frame-budget audit"),
        ("saves", cmd_saves, "Inspect user:// save files, validate JSON/binary schemas, and debug data"),
        ("syntax", cmd_syntax, "Query/learn documentation or scan migration hints"),
        ("lock", cmd_lock, "Multi-agent advisory file lease manager and SHA-256 write-off journal"),
        ("graph", cmd_graph, "Persistent graph status, refresh or scoped query"),
        ("context", cmd_context, "Inspect/refresh persistent project guidance"),
        ("clean", cmd_clean, "Delete ephemeral captures and QA evidence"),
    ):
        tool = sub.add_parser(name, parents=[common], help=help_text, description=help_text)
        tool.set_defaults(handler=callback)
        commands[name] = tool
    pt = commands["plan-task"]
    pt.add_argument("task_desc", nargs="?", help="Task description string")
    pt.add_argument("--task", dest="opt_task", help="Task description string")
    pt.add_argument("--files", nargs="*", default=[], help="Target files to modify")
    pt.add_argument("--multi-agent", action="store_true", help="Flag concurrent multi-agent write execution")
    so = commands["scene-outline"]
    so.add_argument("scene", nargs="?", help="Project-relative or res:// scene")
    so.add_argument("--scene", dest="opt_scene", help="Project-relative or res:// scene")
    md = commands["mockup-dissect"]
    md.add_argument("--scene", default="modals/game_ui.tscn", help="Target UI .tscn scene (auto-discovered if default missing)")
    md.add_argument("--mockup", default="docs/art/farm_hud_polish_v2/mockup_hd_v03_flat.png", help="Reference mockup PNG")
    md.add_argument("--out-dir", default="artifacts/ui_pipeline", help="Artifact output directory")
    md.add_argument("--check-prereqs", action="store_true", help="Verify Stage 0 prerequisites and user art style direction gate")
    mg = commands["mockup-grade"]
    mg.add_argument("--manifest", default="artifacts/ui_pipeline/dissection_manifest.json", help="Path to dissection_manifest.json")
    mg.add_argument("--tolerance", type=float, default=2.0, help="Margin tolerance in pixels (default: 2.0)")
    base = commands["baseline"]
    base.add_argument("--save", action="store_true", help="Save the current scene layout as the reference baseline")
    base.add_argument("--check", action="store_true", help="Check current scene layout against the reference baseline")
    base.add_argument("--scene", help="Target scene (default: project main scene)")
    base.add_argument("--tolerance", type=float, default=1.0, help="Pixel position/size tolerance (default: 1.0px)")
    cap = commands["capture"]
    selection = cap.add_mutually_exclusive_group()
    selection.add_argument("--scene", help="Project-relative or res:// scene")
    selection.add_argument("--scenes", nargs="+", help="Capture multiple scene paths and produce review grids")
    selection.add_argument("--all-scenes", action="store_true", help="Discover project .tscn scenes; failures do not stop the batch")
    cap.add_argument("--width", type=int, help="Override project viewport width")
    cap.add_argument("--height", type=int, help="Override project viewport height")
    cap.add_argument("--output", help="Explicit project-relative artifact directory (default: unique directory)")
    cap.add_argument("--renderer", choices=["gl_compatibility", "mobile", "forward_plus"], help="Explicit renderer override; default preserves the project")
    cap.add_argument("--clean", action="store_true", help="Purge older debug captures before capturing")
    cap.add_argument("--keep", type=int, default=5, help="Number of debug capture sessions to retain (default: 5)")
    cap.add_argument("--prop", action="append", default=[], help="Runtime property override, e.g. label.text='Hello' or score=10")
    cap.add_argument("--inputs", help="JSON string or comma-separated list of scripted input actions/keys")
    cap.add_argument("--input-file", help="Path to JSON file containing scripted input sequence")
    cap.add_argument("--fixed-fps", type=int, help="Force physics/render FPS for deterministic capture")
    cap.add_argument("--include-components", action="store_true", help="Include component/widget scenes when running with --all-scenes")
    ast = commands["assets"]
    ast.add_argument("target", nargs="?", help="Specific asset file to audit/process/grade (default: all project assets)")
    ast.add_argument("--audit", action="store_true", help="Audit asset alpha bounding box, padding, and fringes (default)")
    ast.add_argument("--process", action="store_true", help="Process/clean target asset")
    ast.add_argument("--grade", action="store_true", help="Evaluate 3-tier rubric and store in .harness/asset-manifest.json")
    ast.add_argument("--defringe", action="store_true", help="Clean semi-transparent matte fringe")
    ast.add_argument("--crop-alpha", action="store_true", help="Crop canvas to tight non-zero alpha bounding box")
    ast.add_argument("--scale", type=int, default=1, help="Nearest-neighbor integer scale multiplier")
    ast.add_argument("--output", help="Output path for processed image (default: overwrite target)")
    ast.add_argument("--grid", type=int, default=16, help="Native pixel grid size for alignment audit (default: 16)")
    ast.add_argument("--t1", type=float, help="Tier 1 Technical Hygiene score (0-10)")
    ast.add_argument("--t2", type=float, help="Tier 2 Artistic Consistency score (0-10)")
    ast.add_argument("--t3", type=float, help="Tier 3 Functional Clarity score (0-10)")
    ast.add_argument("--scores", help="JSON dictionary of rubric scores")
    adt = commands["audit"]
    adt.add_argument("--physics", action="store_true", help="Audit 2D/3D collision layer/mask matrix, missing colliders, and Y-sort")
    adt.add_argument("--exports", action="store_true", help="Scan scripts for hardcoded gameplay magic numbers that should be @export")
    adt.add_argument("--signals", action="store_true", help="Audit signal connections to ensure target methods exist on receivers")
    adt.add_argument("--perf", action="store_true", help="Detect expensive queries (get_node, $, find_child, load) in _process loops")
    adt.add_argument("--scene-first", action="store_true", help="Audit Scene-First UI policy (flags programmatic Button/Label.new)")
    sv = commands["saves"]
    sv.add_argument("--dir", help="Custom save directory to inspect (default: user:// and project saves/)")
    cln = commands["clean"]
    cln.add_argument("--audit", action="store_true", help="Scan repo hygiene, dangling temporary files, and uncommitted debug caches without deleting")
    cln.add_argument("--captures", action="store_true", help="Clean debug screenshots (default if no target specified)")
    cln.add_argument("--qa-evidence", action="store_true", help="Clean qa-evidence/ review directories")
    cln.add_argument("--all", action="store_true", help="Clean all ephemeral captures and QA evidence")
    lck = commands["lock"]
    lck.add_argument("lock_action", choices=["acquire", "release", "write-off", "check", "status", "prune"], nargs="?", default="status", help="Lock operation")
    lck.add_argument("paths", nargs="*", default=[], help="Target file paths for acquire, release, write-off, or check")
    lck.add_argument("--agent", default="", help="Agent identifier (use 'vscode-user' for human priority)")
    lck.add_argument("--task", default="", help="Task identifier")
    lck.add_argument("--ttl", type=float, default=300, help="Lease TTL in seconds (default: 300)")
    lck.add_argument("--summary", default="", help="Change summary (required for write-off)")
    lck.add_argument("--force", action="store_true", help="Force release or preemption regardless of owner")
    lck.add_argument("--limit", type=int, default=10, help="Number of recent journal entries for status")
    commands["validate"].add_argument("--engine", action="store_true", help="Run engine parse/load checks using existing imports; executes project code")
    commands["validate"].add_argument("--orphans", action="store_true", help="Scan for unreferenced asset files")
    commands["validate"].add_argument("--uid", action="store_true", help="Verify all uid:// references map to declared resources")
    commands["test"].add_argument("--list", action="store_true")
    commands["test"].add_argument("--suite", help="Project-relative tests/**/test_*.gd path")
    commands["test"].add_argument("--tier", choices=["minor-doc", "minor-visual", "minor-logic", "smoke", "sanity", "regression"], help="Proportionate test tier to run")
    commands["test"].add_argument("--changed", action="store_true", help="Only run tests related to git-changed files")
    commands["test"].add_argument("--strict-leaks", action="store_true", help="Fail on Godot shutdown resource/ObjectDB leaks")
    syn = commands["syntax"]
    action = syn.add_mutually_exclusive_group()
    action.add_argument("--scan")
    action.add_argument("--query")
    action.add_argument("--learn-practice-key")
    action.add_argument("--learn-syntax-old")
    for flag in ("learn-practice-desc", "learn-syntax-new", "learn-syntax-context"):
        syn.add_argument("--" + flag)
    for flag in ("min-version", "max-version-exclusive", "matcher", "literal", "source-url"):
        syn.add_argument("--" + flag)
    syn.add_argument("--verified", action="store_true")
    graph = commands["graph"]
    action = graph.add_mutually_exclusive_group()
    action.add_argument("--refresh", action="store_true")
    action.add_argument("--query")
    graph.add_argument("--budget", type=int, default=1500)
    commands["context"].add_argument("--refresh", action="store_true")
    return parser, commands


_COMPACT_PRESERVE_KEYS = {
    "plan-task": (
        "task", "task_type", "triage_category", "change_class", "tier",
        "caveman_mode", "caveman_reason", "required_skills", "matched_playbooks",
        "skip_graphify", "lock_required", "art_style_check", "ask_user_art_style",
        "affected_files", "graph_neighbors", "verification_commands",
        "Verification_plan", "verification_plan", "suggested_commands", "steps",
    ),
    "scene-outline": ("outline",),
    "mockup-dissect": (
        "scene", "probe_mode", "measured_layers_px", "control_count",
        "styled_control_count", "dissection_manifest", "handoff_manifest",
        "pipeline_connection", "prerequisites", "art_style_configured",
        "art_style_direction", "ask_user_art_style", "pillow_available",
        "scene_exists", "ok", "passed",
    ),
    "mockup-grade": (
        "scene", "passed", "probe_mode", "required_patch_margin_px",
        "graded_control_count", "failed_count", "failed_components",
        "pipeline_connection",
    ),
    "lock": (
        "action", "lock_status", "agent_id", "task_id", "acquired", "preempted",
        "released", "skipped", "conflicts", "checked", "locked", "files",
        "file_hashes", "write_off_summary", "active_count", "active_leases",
        "journal", "pruned_count", "remaining_count", "ttl", "expires_at",
    ),
}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    args = None
    requested = "info"
    ctx_hash = ""
    ctx_stale = False
    try:
        parser, commands = build_parser()
        requested = next((v for v in argv if v in commands), "info")
        if "--json" in argv and ("--help" in argv or "-h" in argv):
            selected = next((commands[v] for v in argv if v in commands), parser)
            print(json.dumps(result("help", "CLI help", output=selected.format_help()), ensure_ascii=False))
            return 0
        args = parser.parse_args(argv)
        for key, default in (("project", None), ("godot", None), ("timeout", 30), ("json", False), ("compact", False), ("out", None), ("full", False)):
            if not hasattr(args, key):
                setattr(args, key, default)
        args.root = resolve_project(args.project, required=requested not in ("help", "plan-task"))
        args.commands = commands
        args.context = {"project_root": _to_posix(args.root)}
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise HarnessError("INVALID_ARGUMENT", "Timeout must be positive")
        response = args.handler(args)
        ctx_hash, ctx_stale, _ = sync_project_state_cache(
            args.root,
            args.context if args.context.get("engine_version") else None,
        )
        response["context"] = args.context
    except HarnessError as exc:
        response = result(getattr(args, "command", None) or requested, str(exc), [finding(exc.code, str(exc))],
                          status="unsupported" if exc.code in ("ENGINE_UNSUPPORTED", "ISOLATION_UNSUPPORTED", "TOOL_UNAVAILABLE") else "failed")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        response = result(getattr(args, "command", None) or requested, str(exc), [finding("INVALID_DATA", str(exc))])
    if args is not None and hasattr(args, "context"):
        response["context"] = args.context
        if args.command in ("capture", "validate", "baseline", "audit", "assets") or (args.command == "test" and not args.list and response["status"] != "skipped") or (args.command == "syntax" and args.scan):
            try:
                record_checkpoint(args.root, response)
            except (OSError, HarnessError) as exc:
                response["status"] = "failed"
                response["findings"].append(finding("CHECKPOINT_FAILED", str(exc)))
    if getattr(args, "compact", False):
        if "findings" in response and len(response["findings"]) > 5:
            response["omitted_findings_count"] = len(response["findings"]) - 5
            response["findings"] = response["findings"][:5]
        if "artifacts" in response and len(response["artifacts"]) > 5:
            response["omitted_artifacts_count"] = len(response["artifacts"]) - 5
            response["artifacts"] = response["artifacts"][:5]
        response["compact"] = True
        cmd_name = response.get("command") or (args.command if args is not None else requested)
        if not getattr(args, "full", False):
            if not ctx_hash and args is not None and hasattr(args, "root"):
                ctx_hash, ctx_stale, _ = sync_project_state_cache(args.root)
            compact_resp = {
                "schema_version": 2,
                "cmd": cmd_name,
                "command": cmd_name,
                "status": response.get("status"),
                "ctx_hash": ctx_hash,
                "ctx_stale": ctx_stale,
                "active_skill": ACTIVE_SKILLS.get(cmd_name, ".agents/skills/core-architecture/SKILL.md"),
                "summary": response.get("summary", ""),
                "findings": response.get("findings", []),
                "next_command": response.get("next_command"),
            }
            if response.get("artifacts"):
                compact_resp["artifacts"] = response["artifacts"]
            if response.get("omitted_findings_count"):
                compact_resp["omitted_findings_count"] = response["omitted_findings_count"]
            if response.get("omitted_artifacts_count"):
                compact_resp["omitted_artifacts_count"] = response["omitted_artifacts_count"]
            for keep_key in _COMPACT_PRESERVE_KEYS.get(cmd_name, ()):
                if keep_key in response:
                    compact_resp[keep_key] = response[keep_key]
            if ctx_stale or response.get("status") not in ("success", "skipped"):
                if response.get("context"):
                    compact_resp["context"] = response["context"]
            response = compact_resp
    response = _normalize_posix_payload(response)
    out_path = getattr(args, "out", None) if args is not None else None
    if out_path:
        target_out = Path(out_path)
        target_out.parent.mkdir(parents=True, exist_ok=True)
        with open(target_out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(response, fh, ensure_ascii=False, indent=None if getattr(args, "compact", False) else 2, sort_keys=True)
            fh.write("\n")
    if "--json" in argv:
        print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    else:
        print(response["summary"])
        print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response["status"] in ("success", "skipped") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
