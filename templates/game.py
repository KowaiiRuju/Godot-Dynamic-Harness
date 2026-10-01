#!/usr/bin/env python3
"""
game.py - Unified Headless QA, Scene Inspection, and Test Runner CLI
Godot Dynamic Harness Template
"""

import os
import re
import sys
import argparse
import subprocess
import shutil
from pathlib import Path

# Godot and this tool both print emoji; the Windows default console codec
# (cp1252) raises UnicodeEncodeError and kills the run. Force UTF-8 first.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.resolve()
CORE_RUNNER = PROJECT_ROOT / "core" / "tools" / "scene_runner.gd"
DOCS_UPDATER = PROJECT_ROOT / "core" / "tools" / "docs_updater.py"
DEFAULT_SCREENSHOT_DIR = PROJECT_ROOT / "screenshots" / "debug"
PROFILE_NAME = "godot_dynamic_harness_profile"

# Godot reports leaked resources as a hard failure at shutdown. That is a leak
# report, not a test result, so it must not flip the exit code on its own.
SHUTDOWN_NOISE = re.compile(
    r"resources still in use at exit|ObjectDB instances leaked|leaked at exit"
)

def get_godot_bin() -> str:
    """Finds the Godot binary with priority on environment variables and PATH."""
    for env_var in ["GODOT4_BIN", "GODOT_BIN"]:
        val = os.environ.get(env_var)
        if val and Path(val).is_file():
            return str(Path(val).resolve())

    candidates = ["godot4", "godot", "Godot"]
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found

    # Windows fallback checks. Prefer the explicit console build, otherwise the
    # .NET/editor variants may be picked up first and fail to boot.
    for base in (Path.home() / "Desktop", Path.home() / "Downloads", Path("C:/")):
        if not base.exists():
            continue
        for pattern in ("Godot*win64*.exe", "Godot*.exe"):
            for exe in sorted(base.glob(pattern)):
                return str(exe.resolve())

    return "godot"

def to_res_path(path: Path) -> str:
    """Godot's --script flag wants a res:// path, not an absolute one.

    Passing an absolute path makes the engine silently fail to resolve the
    script on Windows, which reads as "the runner does nothing".
    """
    try:
        return "res://" + path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()

def triage(stderr: str, stdout: str) -> list:
    """Return only genuine errors, discarding Godot's shutdown leak report."""
    found = []
    for line in (stderr + "\n" + stdout).splitlines():
        if not line.strip() or SHUTDOWN_NOISE.search(line):
            continue
        if "SCRIPT ERROR" in line or "Parse Error" in line or line.startswith("ERROR:"):
            found.append(line.rstrip())
    return found

def run_headless_godot(args: list, extra_env: dict = None, capture_mode: bool = False) -> int:
    """Runs Godot with an isolated APPDATA profile and returns a real exit code.

    In capture mode we must NOT pass --headless: that disables rendering, so
    root.get_texture().get_image() returns an empty image and the PNG is blank.
    Godot 4.7 on Windows additionally deadlocks when sharing the default
    profile with an open Editor, hence the redirect.
    """
    godot_bin = get_godot_bin()
    env = os.environ.copy()

    # Isolate user profile on Windows
    if sys.platform == "win32":
        temp_appdata = Path(env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / PROFILE_NAME
        temp_appdata.mkdir(parents=True, exist_ok=True)
        env["APPDATA"] = str(temp_appdata)
    env["PYTHONIOENCODING"] = "utf-8"

    if extra_env:
        env.update(extra_env)

    if capture_mode:
        cmd = [godot_bin, "--rendering-method", "gl_compatibility",
               "--audio-driver", "Dummy"] + args
    else:
        cmd = [godot_bin, "--headless"] + args

    print(f"Running: {' '.join(cmd)}")
    si = None
    if sys.platform == "win32" and capture_mode:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.dwShowWindow = 0  # SW_HIDE

    proc = subprocess.run(
        cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True,
        text=True, encoding="utf-8", errors="replace", startupinfo=si,
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    errors = triage(proc.stderr or "", proc.stdout or "")
    if errors:
        print("Errors:", file=sys.stderr)
        for e in errors[:20]:
            print(f"  {e}", file=sys.stderr)
        # A runner that printed errors but still exited 0 is a false pass.
        return proc.returncode or 1
    return proc.returncode

TSCN_LINT = PROJECT_ROOT / "core" / "tools" / "tscn_lint.py"
SCENE_SWEEP = PROJECT_ROOT / "core" / "tools" / "scene_sweep.py"
UI_AUDIT = PROJECT_ROOT / "core" / "tools" / "ui_audit.py"
HANDOFF = PROJECT_ROOT / "core" / "tools" / "handoff.py"
CLEANUP = PROJECT_ROOT / "core" / "tools" / "cleanup.py"


def auto_clean() -> None:
    """Drop the isolated APPDATA profile and bytecode after every run.

    The profile is created fresh each invocation and is pure byproduct, so
    leaving it behind grows without bound across sessions. Never runs for
    `clean` itself, or for a dry run, which must not delete anything.
    """
    if "clean" in sys.argv or "--dry-run" in sys.argv:
        return
    if "--keep-profile" in sys.argv:
        return
    tool = CLEANUP
    if not tool.exists():
        return
    try:
        subprocess.run([sys.executable, str(tool)], cwd=str(PROJECT_ROOT),
                       capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_tool(name: str, argv: list) -> int:
    """Run a sibling tool in core/tools/ and propagate its exit code."""
    tool = {"lint": TSCN_LINT, "sweep": SCENE_SWEEP, "audit": UI_AUDIT,
            "handoff": HANDOFF, "clean": CLEANUP}[name]
    if not tool.exists():
        print(f"Error: {tool.name} is missing from core/tools/.")
        return 1
    return subprocess.run([sys.executable, str(tool)] + argv).returncode


def cmd_info(args):
    print("=== Godot Dynamic Harness Environment ===")
    godot_bin = get_godot_bin()
    print(f"Detected Godot Binary: {godot_bin}")
    print(f"Project Root:          {PROJECT_ROOT}")
    print(f"Runner Script:         {CORE_RUNNER.exists()} ({CORE_RUNNER})")
    tests = list((PROJECT_ROOT / "tests").glob("test_*.gd")) if (PROJECT_ROOT / "tests").exists() else []
    scenes = [p for p in PROJECT_ROOT.rglob("*.tscn")
              if not SKIP_DIRS.intersection(p.parts)]
    print(f"Discovered Tests:      {len(tests)}")
    print(f"Discovered Scenes:    {len(scenes)}")
    print("Tools:")
    for label, tool in (("lint", TSCN_LINT), ("sweep", SCENE_SWEEP),
                        ("audit", UI_AUDIT), ("handoff", HANDOFF),
                        ("syntax", DOCS_UPDATER)):
        print(f"  {label:<8} {'ok' if tool.exists() else 'MISSING'}  {tool.name}")

def cmd_capture(args):
    if not args.scene:
        print("Error: --scene <path> is required.")
        sys.exit(1)
    if not CORE_RUNNER.exists():
        print(f"Error: runner not found at {CORE_RUNNER}")
        sys.exit(1)
    if not args.scene.startswith("res://"):
        print(f"Error: --scene must be a res:// path, got '{args.scene}'.")
        sys.exit(1)

    extra_env = {
        "GAME_TARGET_SCENE": args.scene,
        "GAME_OUTPUT_DIR": str(DEFAULT_SCREENSHOT_DIR),
        "GAME_VIEWPORT_WIDTH": str(args.width),
        "GAME_VIEWPORT_HEIGHT": str(args.height),
    }

    code = run_headless_godot(
        ["--path", str(PROJECT_ROOT), "--script", to_res_path(CORE_RUNNER)],
        extra_env=extra_env, capture_mode=True,
    )
    if code == 0:
        print(f"Screenshot + manifest written to {DEFAULT_SCREENSHOT_DIR}")
    sys.exit(code)

def cmd_test(args):
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        print("No tests/ directory found.")
        return

    test_files = sorted(tests_dir.glob("test_*.gd"))
    if args.suite:
        wanted = args.suite
        test_files = [t for t in test_files if t.stem == wanted or t.name == wanted]
        if not test_files:
            print(f"No test suite matched '{wanted}'.")
            sys.exit(1)

    if args.list:
        print("Available Test Suites:")
        for t in test_files:
            print(f" - {t.name}")
        return

    failed = []
    for t in test_files:
        print(f"\n--- Running: {t.name} ---")
        code = run_headless_godot(
            ["--path", str(PROJECT_ROOT), "--script", to_res_path(t)])
        if code != 0:
            failed.append(t.name)

    print(f"\n=== Test Summary: {len(test_files) - len(failed)}/{len(test_files)} passed ===")
    if failed:
        for name in failed:
            print(f"  FAILED: {name}")
        sys.exit(1)

SKIP_DIRS = {"addons", ".godot", "builds", ".git", "graphify-out", "__pycache__"}

# Anchored so "MyLabel.new()" is not reported as "Label.new()".
FORBIDDEN = {
    "Control.new()": r"(?<![\w.])(?:[A-Za-z_]\w*\.)?Control\.new\s*\(",
    "Button.new()": r"(?<![\w.])(?:[A-Za-z_]\w*\.)?Button\.new\s*\(",
    "Label.new()": r"(?<![\w.])(?:[A-Za-z_]\w*\.)?Label\.new\s*\(",
    "Panel.new()": r"(?<![\w.])(?:[A-Za-z_]\w*\.)?Panel\.new\s*\(",
    "TextureRect.new()": r"(?<![\w.])(?:[A-Za-z_]\w*\.)?TextureRect\.new\s*\(",
    "add_theme_stylebox_override": r"\badd_theme_stylebox_override\s*\(",
}
FORBIDDEN_RE = {name: re.compile(pat) for name, pat in FORBIDDEN.items()}

def strip_comments(line: str) -> str:
    """Remove trailing # comments and quoted strings to avoid false positives."""
    out, in_str, quote = [], False, ""
    for i, ch in enumerate(line):
        if in_str:
            if ch == quote and line[i - 1] != "\\":
                in_str = False
            continue
        if ch in "\"'":
            in_str, quote = True, ch
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out)

def cmd_validate(args):
    print("=== Static Project Validation ===")
    violations = 0
    scanned = 0
    for gd_file in PROJECT_ROOT.rglob("*.gd"):
        if SKIP_DIRS.intersection(gd_file.parts):
            continue
        try:
            lines = gd_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            print(f"  (skipped {gd_file.name}: {exc})")
            continue
        scanned += 1
        for n, line in enumerate(lines, start=1):
            clean = strip_comments(line)
            for name, rx in FORBIDDEN_RE.items():
                if rx.search(clean):
                    rel = gd_file.relative_to(PROJECT_ROOT)
                    print(f"Rule violation {rel}:{n}: '{name}'. UI must live in .tscn.")
                    violations += 1

    # Broken ExtResource paths: the single most common cause of a scene that
    # will not load at runtime.
    broken = 0
    for tscn in PROJECT_ROOT.rglob("*.tscn"):
        if SKIP_DIRS.intersection(tscn.parts):
            continue
        try:
            for line in tscn.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r'\[ext_resource\s+type="[^"]+"\s+path="([^"]+)"', line)
                if not m:
                    continue
                target = m.group(1)
                if not target.startswith("res://"):
                    continue
                if not (PROJECT_ROOT / target[6:]).exists():
                    rel = tscn.relative_to(PROJECT_ROOT)
                    print(f"Broken ExtResource {rel}: missing {target}")
                    broken += 1
        except OSError:
            continue

    print(f"\nScanned {scanned} .gd files.")
    print("OK: no Scene-First UI violations." if violations == 0
          else f"{violations} UI rule violation(s).")
    print("OK: no broken ExtResource paths." if broken == 0
          else f"{broken} broken ExtResource path(s).")
    # Nonzero so CI can gate on this instead of only reading the text.
    sys.exit(1 if (violations or broken) else 0)

def cmd_syntax(args):
    print("=== GDScript Syntax & Version Checking ===")
    if not DOCS_UPDATER.exists():
        print(f"Error: {DOCS_UPDATER.name} tool is missing.")
        sys.exit(1)
    
    if args.query:
        return subprocess.run([sys.executable, str(DOCS_UPDATER),
                               "query", args.query]).returncode
    if args.scan:
        scan_target = Path(args.scan)
        if not scan_target.is_absolute():
            scan_target = PROJECT_ROOT / scan_target
        if scan_target.is_file():
            files_to_scan = [scan_target]
        elif scan_target.is_dir():
            files_to_scan = sorted(scan_target.rglob("*.gd"))
        else:
            print(f"Error: '{args.scan}' is neither a file nor a directory.")
            sys.exit(1)

        if not files_to_scan:
            print("No .gd files found to scan.")
            return 0

        failed = 0
        for f in files_to_scan:
            result = subprocess.run(
                [sys.executable, str(DOCS_UPDATER), "scan", str(f)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                print(result.stdout.rstrip())
                if result.stderr:
                    print(result.stderr.rstrip())
                failed += 1

        if failed > 0:
            print(f"{failed}/{len(files_to_scan)} files contain deprecated syntax.")
            sys.exit(1)
        print(f"All {len(files_to_scan)} files passed syntax validation.")
        return 0

    if args.learn_practice_key and args.learn_practice_desc:
        return subprocess.run(
            [sys.executable, str(DOCS_UPDATER), "learn",
             "--practice-key", args.learn_practice_key,
             "--practice-desc", args.learn_practice_desc]).returncode
    if args.learn_syntax_old and args.learn_syntax_new:
        cmd = [sys.executable, str(DOCS_UPDATER), "learn",
               "--syntax-old", args.learn_syntax_old,
               "--syntax-new", args.learn_syntax_new]
        if args.learn_syntax_context:
            cmd.extend(["--syntax-context", args.learn_syntax_context])
        return subprocess.run(cmd).returncode

    parser_syntax.print_help()
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Godot Dynamic Harness CLI")
    subparsers = parser.add_subparsers(dest="command")

    # info
    subparsers.add_parser("info", help="Show environment diagnostics")

    # capture
    p_cap = subparsers.add_parser("capture", help="Capture offscreen scene screenshot")
    p_cap.add_argument("--scene", required=True, help="res:// path to .tscn scene")
    p_cap.add_argument("--width", type=int, default=1280, help="Viewport width")
    p_cap.add_argument("--height", type=int, default=720, help="Viewport height")

    # test
    p_test = subparsers.add_parser("test", help="Run headless test suites")
    p_test.add_argument("--list", action="store_true", help="List discovered test suites")

    # validate
    subparsers.add_parser("validate", help="Audit project for Scene-First UI rules")

    # lint
    p_lint = subparsers.add_parser("lint", help="Static .tscn/.tres integrity check")
    p_lint.add_argument("paths", nargs="*", help="limit to these files or dirs")
    p_lint.add_argument("--json", action="store_true")

    # sweep
    p_sweep = subparsers.add_parser("sweep", help="Load every scene and report failures")
    p_sweep.add_argument("subdir", nargs="?", help="limit to this subdirectory")
    p_sweep.add_argument("--timeout", type=int, default=90)
    p_sweep.add_argument("--list", action="store_true")
    p_sweep.add_argument("--json", action="store_true")

    # audit
    p_audit = subparsers.add_parser("audit", help="Flag layout defects in a scene manifest")
    p_audit.add_argument("manifest", nargs="?", help="path to scene_manifest.json")
    p_audit.add_argument("--min-font", type=int, default=10)
    p_audit.add_argument("--viewport", default="")
    p_audit.add_argument("--tolerance", type=int, default=2)

    # handoff
    p_ho = subparsers.add_parser("handoff",
                                 help="Record or load a cross-agent session handoff")
    p_ho.add_argument("handoff_cmd", choices=["save", "load", "show"])
    p_ho.add_argument("--task")
    p_ho.add_argument("--next", action="append")
    p_ho.add_argument("--agent")
    p_ho.add_argument("--ide")
    p_ho.add_argument("--verify", action="store_true")
    p_ho.add_argument("--resume", action="store_true")
    p_ho.add_argument("--json", action="store_true")

    # clean
    p_cl = subparsers.add_parser("clean",
                                 help="Remove generated test scripts, manifests, and captures")
    p_cl.add_argument("--all", action="store_true",
                      help="also remove captures and manifests, not just scratch scripts")
    p_cl.add_argument("--keep-captures", action="store_true",
                      help="with --all, keep PNGs but delete manifests")
    p_cl.add_argument("--dry-run", action="store_true", help="list without deleting")
    
    # syntax
    p_syntax = subparsers.add_parser("syntax", help="Check files against the latest GDScript docs and version changes log")
    p_syntax.add_argument("--query", help="Query a specific keyword in the JSON log")
    p_syntax.add_argument("--scan", help="Scan a file or directory for deprecated Godot 3.x syntax")
    p_syntax.add_argument("--learn-practice-key", help="Key name for a newly discovered best practice")
    p_syntax.add_argument("--learn-practice-desc", help="Description of the best practice")
    p_syntax.add_argument("--learn-syntax-old", help="Old deprecated syntax to learn")
    p_syntax.add_argument("--learn-syntax-new", help="New correct syntax to learn")
    p_syntax.add_argument("--learn-syntax-context", help="Context for the syntax change")

    args = parser.parse_args()
    if not args.command or args.command == "info":
        cmd_info(args)
    elif args.command == "capture":
        cmd_capture(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "lint":
        sys.exit(run_tool("lint", args.paths + (["--json"] if args.json else [])))
    elif args.command == "sweep":
        argv = [args.subdir] if args.subdir else []
        if args.list:
            argv.append("--list")
        if args.json:
            argv.append("--json")
        argv += ["--timeout", str(args.timeout)]
        sys.exit(run_tool("sweep", argv))
    elif args.command == "audit":
        argv = [args.manifest] if args.manifest else []
        argv += ["--min-font", str(args.min_font), "--tolerance", str(args.tolerance)]
        if args.viewport:
            argv += ["--viewport", args.viewport]
        sys.exit(run_tool("audit", argv))
    elif args.command == "handoff":
        argv = [args.handoff_cmd]
        if args.handoff_cmd == "save":
            if args.task:
                argv += ["--task", args.task]
            for n in args.next or []:
                argv += ["--next", n]
            if args.agent:
                argv += ["--agent", args.agent]
            if args.ide:
                argv += ["--ide", args.ide]
            if args.verify:
                argv.append("--verify")
            if args.resume:
                argv.append("--resume")
        if args.handoff_cmd == "show" and args.json:
            argv.append("--json")
        sys.exit(run_tool("handoff", argv))
    elif args.command == "clean":
        sys.exit(run_tool("clean", (
            ["--all"] if args.all else []) +
            (["--keep-captures"] if args.keep_captures else []) +
            (["--dry-run"] if args.dry_run else [])))
    elif args.command == "syntax":
        sys.exit(cmd_syntax(args) or 0)

if __name__ == "__main__":
    try:
        main()
    finally:
        auto_clean()
