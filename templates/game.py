#!/usr/bin/env python3
"""Godot project tools. Standard library only; JSON stdout is an agent contract."""
import argparse
import concurrent.futures
import datetime
import hashlib
import importlib.util
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
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
TOOLS_DIR = PROJECT_ROOT / "core" / "tools"
CORE_RUNNER = TOOLS_DIR / "scene_runner.gd"
DOCS_UPDATER = TOOLS_DIR / "docs_updater.py"
SKIP_DIRS = {".agents", ".harness", ".godot", ".git", ".venv", "venv", "addons", "builds", "screenshots", "graphify-out", "qa-evidence", "__pycache__"}
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


def result(command, summary, findings=None, artifacts=None, status=None, **extra):
    findings = findings or []
    return dict(schema_version=1, command=command,
                status=status or ("failed" if findings else "success"), context={},
                summary=summary, findings=findings, artifacts=artifacts or [], **extra)


def finding(code, message, **location):
    return dict(code=code, message=message, **location)


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
    for log_output in (completed.stdout, completed.stderr):
        if log_output and (log or completed.returncode or ENGINE_ERRORS.search(completed.stdout + completed.stderr)):
            print(log_output.rstrip(), file=sys.stderr)
    return completed


def load_tool(name):
    spec = importlib.util.spec_from_file_location("gdh_" + name, TOOLS_DIR / (name + ".py"))
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


def resolve_project(explicit=None):
    candidates = [resolved_path(Path(explicit))] if explicit else [PROJECT_ROOT, Path.cwd(), *Path.cwd().parents]
    for root in candidates:
        if (root / "project.godot").is_file():
            return root.resolve()
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
                          mutating=name in ("capture", "test", "validate", "syntax", "graph", "context", "clean"),
                          mutation_condition={"syntax": "Only --learn-* modifies rules; --scan records an outcome", "graph": "--refresh rebuilds project graph/state", "context": "--refresh updates managed context", "test": "Execution writes isolated user data and a checkpoint", "capture": "Writes capture artifacts and a checkpoint", "validate": "Writes a checkpoint; engine execution may write caches", "clean": "Deletes ephemeral screenshots and QA review evidence"}.get(name),
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
        atomic_write(graph, json.dumps(data, indent=2) + "\n")
        atomic_write(safe_target(args.root, ".harness/graph-state.json"), json.dumps(
            {"source_digest": digest, "graph_digest": hashlib.sha256(graph.read_bytes()).hexdigest()}, indent=2) + "\n")
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
    overview = "# Project overview\n\n" + "\n".join(f"- {key}: {json.dumps(value, ensure_ascii=False)}" for key, value in settings.items())
    overview += f"\n- Engine: {context.get('engine_version', 'not discovered')}\n- Scripts: {len(project_files(root, '.gd'))}; scenes: {len(project_files(root, '.tscn'))}\n\nAuthored settings are not runtime-effective overrides. Genre and architecture must be verified from source. Keep project-specific decisions outside this managed block."
    commands = """# Tool commands

Run from the project root. Use --project and --godot to override discovery.

- python game.py info --json: engine/project/capabilities/freshness.
- python game.py graph --refresh --timeout 120 --json: create/update persistent AST graph.
- python game.py graph --query "your codebase question" --json: bounded navigation before investigation.
- python game.py validate --json: policy and resource-reference hints.
- python game.py validate --engine --json: parse/load checks using existing imports; executes project code.
- python game.py syntax --scan . --json: applicable migration hints, not compilation.
- python game.py syntax --query export --json: query rule/practice notes.
- python game.py test --list --json: recursive inventory, not executed-test proof.
- python game.py capture --json: render project main scene/default viewport (auto-prunes debug captures to 5 newest).
- python game.py capture --clean --json: clean older debug captures before rendering.
- python game.py capture --scene res://Main.tscn --width 720 --height 1280 --json: explicit capture.
- python game.py capture --scenes res://Menu.tscn res://Levels/Level01.tscn --json: selected scenes with labeled review grids.
- python game.py capture --all-scenes --json: all discovered scenes, up to three concurrent renders.
- python game.py clean --captures --json: delete ephemeral debug captures in screenshots/debug.
- python game.py clean --all --json: delete debug captures and qa-evidence directories.
- python game.py context --refresh --json: refresh overview while preserving user additions.

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
        atomic_write(safe_target(args.root, ".harness/context-state.json"), json.dumps({"source_digest": fingerprint(args.root)}) + "\n")
    paths = [safe_target(args.root, p) for p in ("docs/harness/PROJECT.md", "docs/harness/TOOLS.md", "docs/harness/CHECKPOINT.md")]
    return result("context", "Persistent project context", artifacts=[str(p) for p in paths if p.is_file()], graph=graph_state(args.root))


def record_checkpoint(root, response):
    outcome = {k: response[k] for k in ("command", "status", "summary", "findings", "artifacts")}
    outcome["time_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    outcome["source_digest"] = fingerprint(root)
    outcome["engine_version"] = response["context"].get("engine_version")
    atomic_write(safe_target(root, ".harness/checkpoint.json"), json.dumps(outcome, indent=2) + "\n")
    path = safe_target(root, "docs/harness/CHECKPOINT.md")
    body = "# Last tool outcome\n\n```json\n" + json.dumps(outcome, indent=2) + "\n```\n\nThis records tool evidence only. It does not certify gameplay, device acceptance or IDE compliance. Add handoff notes outside the managed block."
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


def command_findings(completed, label):
    if completed.returncode or ENGINE_ERRORS.search(completed.stdout + completed.stderr):
        locations = sorted(set(re.findall(r"(res://[^()\r\n]+):(\d+)", completed.stdout + completed.stderr)))
        if locations:
            return [finding("COMMAND_FAILED", f"{label} failed (exit {completed.returncode}); see stderr logs", file=path, line=int(line)) for path, line in locations]
        return [finding("COMMAND_FAILED", f"{label} failed (exit {completed.returncode}); see stderr logs")]
    return []


def cmd_info(args):
    args.context.update(inspect_context(args.root, args.godot, args.timeout))
    state = safe_target(args.root, ".harness/context-state.json")
    stale = not state.is_file() or json.loads(state.read_text(encoding="utf-8")).get("source_digest") != fingerprint(args.root)
    return result("info", "Project and engine discovered", capabilities=capabilities(args), graph=graph_state(args.root), context_stale=stale,
                  tests=[str(p.relative_to(args.root)) for p in discover_tests(args.root)],
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
    completed = run_headless_godot(["--script", str(CORE_RUNNER)],
        {"GAME_TARGET_SCENE": scene, "GAME_OUTPUT_DIR": str(output),
         "GAME_VIEWPORT_WIDTH": str(args.width or 0), "GAME_VIEWPORT_HEIGHT": str(args.height or 0), "GAME_CAPTURE_ID": capture_id},
        capture_mode=True, root=args.root, godot=args.context["engine_binary"], timeout=args.timeout, renderer=args.renderer)
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
                  capture=data, renderer_override=args.renderer)


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
            shutil.rmtree(victim, ignore_errors=True)
            deleted.append(str(victim.relative_to(root)))
    except (OSError, PermissionError):
        pass
    return deleted, freed_bytes


def cmd_clean(args):
    """Delete ephemeral debug screenshots and QA review evidence."""
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
            shutil.rmtree(debug_dir, ignore_errors=True)
            deleted.append("screenshots/debug")
        sc_dir = safe_target(args.root, "screenshots")
        if sc_dir.is_dir() and not any(sc_dir.iterdir()):
            shutil.rmtree(sc_dir, ignore_errors=True)

    if clean_qa or clean_all:
        qa_dir = safe_target(args.root, "qa-evidence")
        if qa_dir.is_dir():
            for f in qa_dir.rglob("*"):
                if f.is_file():
                    freed += f.stat().st_size
            shutil.rmtree(qa_dir, ignore_errors=True)
            deleted.append("qa-evidence")

    human_freed = f"{freed / (1024 * 1024):.1f} MB" if freed >= 1024 * 1024 else f"{freed / 1024:.1f} KB" if freed >= 1024 else f"{freed} bytes"
    summary = f"Cleaned {len(deleted)} capture/evidence item(s) ({human_freed} freed)" if deleted else "No ephemeral capture artifacts to clean"
    return result("clean", summary, artifacts=deleted, freed_bytes=freed, status="success")


def cmd_capture(args):
    if any(value is not None and value <= 0 for value in (args.width, args.height)):
        raise HarnessError("INVALID_ARGUMENT", "Capture dimensions must be positive")
    args.context.update(inspect_context(args.root, args.godot, args.timeout))
    scenes = args.scenes or (["res://" + p.relative_to(args.root).as_posix() for p in project_files(args.root, ".tscn")] if args.all_scenes else [args.scene or args.context["authored_settings"]["main_scene"]])
    batch = args.scenes is not None or args.all_scenes
    if not scenes:
        return result("capture", "No scenes found; no captures ran", status="skipped")
    scenes = list(dict.fromkeys(scenes))
    if args.output:
        output = safe_target(args.root, args.output)
        if getattr(args, "clean", False) and output.is_dir():
            shutil.rmtree(output, ignore_errors=True)
        output.mkdir(parents=True, exist_ok=True)
    else:
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
    atomic_write(report, json.dumps(captures, indent=2) + "\n")
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
    for suite in suites:
        completed = run_headless_godot(["--script", str(suite)], root=args.root,
                                      godot=args.context["engine_binary"], timeout=args.timeout)
        findings.extend(command_findings(completed, str(suite.relative_to(args.root))))
    return result("test", f"Ran {len(suites)} suite(s)", findings, suites=paths)


def cmd_validate(args):
    findings = []
    engine_checked = False
    files = project_files(args.root, ".gd")
    for path in files:
        content = load_tool("docs_updater").code_text(path.read_text(encoding="utf-8"))
        for line, text in enumerate(content.splitlines(), 1):
            for term in ("Control.new()", "Button.new()", "Label.new()", "add_theme_stylebox_override"):
                if term in text:
                    findings.append(finding("UI_POLICY", f"Scene-First policy: {term}", file=str(path.relative_to(args.root)), line=line))
    scenes = project_files(args.root, ".tscn") + project_files(args.root, ".tres")
    for path in scenes:
        for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for resource in re.findall(r'\bpath="(res://[^"\n]+)"', text):
                try:
                    project_path(args.root, resource)
                except HarnessError as exc:
                    findings.append(finding("RESOURCE_REFERENCE", str(exc), file=str(path.relative_to(args.root)), line=line))
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


def build_parser():
    common = Parser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS, help="Godot project directory")
    common.add_argument("--godot", default=argparse.SUPPRESS, help="Explicit Godot executable")
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS, help="Per subprocess timeout in seconds (default 30)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Emit one structured JSON result")
    parser = Parser(description=__doc__, parents=[common])
    parser.set_defaults(command="info", handler=cmd_info)
    sub = parser.add_subparsers(dest="command")
    commands = {}
    for name, callback, help_text in (("info", cmd_info, "Inspect environment and available tools"),
            ("capture", cmd_capture, "Render a scene and inspect its layout"),
            ("test", cmd_test, "Discover and run recursive SceneTree test suites"),
            ("validate", cmd_validate, "Scan policy/references; --engine also parses/loads resources using existing imports"),
            ("syntax", cmd_syntax, "Query/learn documentation or scan migration hints"),
            ("graph", cmd_graph, "Persistent graph status, refresh or scoped query"),
            ("context", cmd_context, "Inspect/refresh persistent project guidance"),
            ("clean", cmd_clean, "Delete ephemeral captures and QA evidence")):
        tool = sub.add_parser(name, parents=[common], help=help_text, description=help_text)
        tool.set_defaults(handler=callback)
        commands[name] = tool
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
    cln = commands["clean"]
    cln.add_argument("--captures", action="store_true", help="Clean debug screenshots (default if no target specified)")
    cln.add_argument("--qa-evidence", action="store_true", help="Clean qa-evidence/ review directories")
    cln.add_argument("--all", action="store_true", help="Clean all ephemeral captures and QA evidence")
    commands["validate"].add_argument("--engine", action="store_true", help="Run engine parse/load checks using existing imports; executes project code")
    commands["test"].add_argument("--list", action="store_true")
    commands["test"].add_argument("--suite", help="Project-relative tests/**/test_*.gd path")
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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = None
    requested = "info"
    try:
        parser, commands = build_parser()
        requested = next((v for v in argv if v in commands), "info")
        if "--json" in argv and ("--help" in argv or "-h" in argv):
            selected = next((commands[v] for v in argv if v in commands), parser)
            print(json.dumps(result("help", "CLI help", output=selected.format_help())))
            return 0
        args = parser.parse_args(argv)
        for key, default in (("project", None), ("godot", None), ("timeout", 30), ("json", False)):
            if not hasattr(args, key):
                setattr(args, key, default)
        args.root = resolve_project(args.project)
        args.commands = commands
        args.context = {"project_root": str(args.root)}
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise HarnessError("INVALID_ARGUMENT", "Timeout must be positive")
        response = args.handler(args)
        response["context"] = args.context
    except HarnessError as exc:
        response = result(getattr(args, "command", None) or requested, str(exc), [finding(exc.code, str(exc))],
                          status="unsupported" if exc.code in ("ENGINE_UNSUPPORTED", "ISOLATION_UNSUPPORTED", "TOOL_UNAVAILABLE") else "failed")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        response = result(getattr(args, "command", None) or requested, str(exc), [finding("INVALID_DATA", str(exc))])
    if args is not None and hasattr(args, "context"):
        response["context"] = args.context
        if args.command in ("capture", "validate") or (args.command == "test" and not args.list and response["status"] != "skipped") or (args.command == "syntax" and args.scan):
            try:
                record_checkpoint(args.root, response)
            except (OSError, HarnessError) as exc:
                response["status"] = "failed"
                response["findings"].append(finding("CHECKPOINT_FAILED", str(exc)))
    if "--json" in argv:
        print(json.dumps(response, ensure_ascii=False))
    else:
        print(response["summary"])
        print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response["status"] in ("success", "skipped") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
