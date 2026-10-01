#!/usr/bin/env python3
"""
game.py - Unified Headless QA, Scene Inspection, and Test Runner CLI
Godot Dynamic Harness Template
"""

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.resolve()
CORE_RUNNER = PROJECT_ROOT / "core" / "tools" / "scene_runner.gd"
DOCS_UPDATER = PROJECT_ROOT / "core" / "tools" / "docs_updater.py"
DEFAULT_SCREENSHOT_DIR = PROJECT_ROOT / "screenshots" / "debug"
PROFILE_NAME = "godot_dynamic_harness_profile"

def get_godot_bin() -> str:
    """Finds the Godot binary with priority on environment variables and PATH."""
    for env_var in ["GODOT4_BIN", "GODOT_BIN"]:
        val = os.environ.get(env_var)
        if val and shutil.which(val):
            return val

    candidates = ["godot4", "godot", "Godot"]
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found

    # Windows fallback checks
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        for exe in desktop.glob("Godot*.exe"):
            return str(exe)

    return "godot"

def run_headless_godot(args: list, extra_env: dict = None, capture_mode: bool = False) -> int:
    """Runs Godot in headless mode with an isolated APPDATA profile to avoid Editor deadlocks."""
    godot_bin = get_godot_bin()
    env = os.environ.copy()

    # Isolate user profile on Windows
    if sys.platform == "win32":
        temp_appdata = Path(env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / PROFILE_NAME
        temp_appdata.mkdir(parents=True, exist_ok=True)
        env["APPDATA"] = str(temp_appdata)

    if extra_env:
        env.update(extra_env)

    if capture_mode and sys.platform == "win32":
        # Godot 4.7 on Windows often deadlocks or fails rendering completely in --headless.
        # Use an isolated window with Dummy audio and GL Compatibility instead.
        cmd = [godot_bin, "--rendering-method", "gl_compatibility", "--audio-driver", "Dummy"] + args
    else:
        cmd = [godot_bin, "--headless"] + args
        
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return result.returncode

def cmd_info(args):
    print("=== Godot Dynamic Harness Environment ===")
    godot_bin = get_godot_bin()
    print(f"Detected Godot Binary: {godot_bin}")
    print(f"Project Root:          {PROJECT_ROOT}")
    print(f"Runner Script:         {CORE_RUNNER.exists()} ({CORE_RUNNER})")
    tests = list((PROJECT_ROOT / "tests").glob("test_*.gd")) if (PROJECT_ROOT / "tests").exists() else []
    print(f"Discovered Tests:      {len(tests)}")

def cmd_capture(args):
    if not args.scene:
        print("Error: --scene <path> is required.")
        sys.exit(1)

    extra_env = {
        "GAME_TARGET_SCENE": args.scene,
        "GAME_OUTPUT_DIR": str(DEFAULT_SCREENSHOT_DIR),
        "GAME_VIEWPORT_WIDTH": str(args.width),
        "GAME_VIEWPORT_HEIGHT": str(args.height),
    }

    code = run_headless_godot(["--script", str(CORE_RUNNER)], extra_env=extra_env, capture_mode=True)
    sys.exit(code)

def cmd_test(args):
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.exists():
        print("No tests/ directory found.")
        sys.exit(0)

    test_files = list(tests_dir.glob("test_*.gd"))
    if args.list:
        print("Available Test Suites:")
        for t in test_files:
            print(f" - {t.name}")
        return

    failed = 0
    for t in test_files:
        print(f"\n--- Running: {t.name} ---")
        code = run_headless_godot(["--script", str(t)])
        if code != 0:
            failed += 1

    print(f"\n=== Test Summary: {len(test_files) - failed}/{len(test_files)} passed ===")
    if failed > 0:
        sys.exit(1)

def cmd_validate(args):
    print("=== Static Project Validation ===")
    # 1. Check for dynamic UI instantiation antipatterns
    forbidden_terms = ["Control.new()", "Button.new()", "Label.new()", "add_theme_stylebox_override"]
    violations = 0
    for gd_file in PROJECT_ROOT.rglob("*.gd"):
        if any(p in gd_file.parts for p in [".agents", "addons", "core"]):
            continue
        try:
            content = gd_file.read_text(encoding="utf-8", errors="ignore")
            for term in forbidden_terms:
                if term in content:
                    print(f"⚠️ Rule violation in {gd_file.relative_to(PROJECT_ROOT)}: Found '{term}'. UI must be constructed in .tscn.")
                    violations += 1
        except Exception:
            pass

    if violations == 0:
        print("✅ No Scene-First UI rule violations detected.")
    else:
        print(f"❌ Found {violations} UI rule violations.")

def cmd_syntax(args):
    print("=== GDScript Syntax & Version Checking ===")
    if not DOCS_UPDATER.exists():
        print(f"Error: {DOCS_UPDATER.name} tool is missing.")
        sys.exit(1)
    
    if args.query:
        subprocess.run([sys.executable, str(DOCS_UPDATER), "query", args.query])
    elif args.scan:
        scan_target = Path(args.scan)
        if scan_target.is_file():
            files_to_scan = [scan_target]
        else:
            files_to_scan = [
                f for f in scan_target.rglob("*.gd")
                if not any(p in f.parts for p in [".agents", "addons", "core"])
            ]
            
        failed = 0
        for f in files_to_scan:
            result = subprocess.run(
                [sys.executable, str(DOCS_UPDATER), "scan", str(f)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if result.returncode != 0:
                print(result.stdout)
                failed += 1
        
        if failed > 0:
            print(f"❌ Found outdated Godot 3.x syntax in {failed} files.")
            sys.exit(1)
        else:
            print(f"✅ All {len(files_to_scan)} files passed syntax validation.")
    elif args.learn_practice_key and args.learn_practice_desc:
        subprocess.run([sys.executable, str(DOCS_UPDATER), "learn", "--practice-key", args.learn_practice_key, "--practice-desc", args.learn_practice_desc])
    elif args.learn_syntax_old and args.learn_syntax_new:
        cmd = [sys.executable, str(DOCS_UPDATER), "learn", "--syntax-old", args.learn_syntax_old, "--syntax-new", args.learn_syntax_new]
        if args.learn_syntax_context:
            cmd.extend(["--syntax-context", args.learn_syntax_context])
        subprocess.run(cmd)
    else:
        print("Please provide --query <keyword>, --scan <file_or_dir>, or the --learn-practice-* / --learn-syntax-* flags.")

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
    elif args.command == "syntax":
        cmd_syntax(args)

if __name__ == "__main__":
    main()
