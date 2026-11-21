#!/usr/bin/env python3
"""
scene_sweep.py - Load every .tscn in the project and report which ones break.

The hardcoded smoke test can only cover the scenes someone remembered to list.
This discovers them, so a scene that stops loading is caught even if nobody
touched the test file.

Usage:
    python core/tools/scene_sweep.py
    python core/tools/scene_sweep.py scenes/            # limit to a subtree
    python core/tools/scene_sweep.py --timeout 90
    python core/tools/scene_sweep.py --list             # only enumerate
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent.parent
RUNNER = "res://core/tools/sweep_runner.gd"
PROFILE_NAME = "godot_dynamic_harness_profile"
SKIP_DIRS = {".godot", ".git", "builds", "__pycache__", "graphify-out", ".agents", "tests"}

SHUTDOWN_NOISE = re.compile(
    r"resources still in use at exit|ObjectDB instances leaked|leaked at exit")


def to_res(p: Path) -> str:
    try:
        return "res://" + p.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def find_godot() -> str:
    for var in ("GODOT4_BIN", "GODOT_BIN"):
        val = os.environ.get(var)
        if val and Path(val).is_file():
            return str(Path(val).resolve())
    from shutil import which
    for c in ("godot4", "godot", "Godot"):
        if found := which(c):
            return found
    for base in (Path.home() / "Desktop", Path.home() / "Downloads"):
        if base.exists():
            for exe in sorted(base.glob("Godot*win64*.exe")):
                return str(exe.resolve())
    return "godot"


def discover(subdir: str | None) -> list:
    root = PROJECT_ROOT / subdir if subdir else PROJECT_ROOT
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*.tscn")):
        if SKIP_DIRS.intersection(p.parts):
            continue
        out.append(to_res(p))
    return out


def godot_env():
    env = os.environ.copy()
    if sys.platform == "win32":
        prof = Path(env.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / PROFILE_NAME
        prof.mkdir(parents=True, exist_ok=True)
        env["APPDATA"] = str(prof)
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="Load every scene and report failures")
    ap.add_argument("subdir", nargs="?", help="limit to this subdirectory")
    ap.add_argument("--timeout", type=int, default=90, help="per-scene seconds")
    ap.add_argument("--list", action="store_true", help="only enumerate scenes")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    scenes = discover(args.subdir)
    if args.list:
        for s in scenes:
            print(s)
        return 0
    if not scenes:
        print("No .tscn files found.")
        return 0

    results, failed = [], 0
    for scene in scenes:
        cmd = [find_godot(), "--headless", "--audio-driver", "Dummy",
               "--path", str(PROJECT_ROOT), "--script", RUNNER, "--scene", scene]
        try:
            proc = subprocess.run(cmd, env=godot_env(), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=args.timeout)
            errs = [l for l in (proc.stderr or "").splitlines()
                    if ("SCRIPT ERROR" in l or l.startswith("ERROR:")) and not SHUTDOWN_NOISE.search(l)]
            ok = proc.returncode == 0 and not errs
        except subprocess.TimeoutExpired:
            errs, ok = [f"timeout after {args.timeout}s"], False
        results.append({"scene": scene, "ok": ok, "errors": errs[:5]})
        if not ok:
            failed += 1
        print(("OK   " if ok else "FAIL ") + scene)
        for e in errs[:3]:
            print("      " + e)

    if args.json:
        print(json.dumps(results, indent=2))
    print(f"\n{len(scenes) - failed}/{len(scenes)} scenes load cleanly.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
