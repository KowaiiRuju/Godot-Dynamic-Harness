#!/usr/bin/env python3
"""
cleanup.py - Remove QA byproducts so the repo does not bloat.

Visual QA and debugging generate files that are useful for exactly one run.
Leaving them in the tree bloats the repo and makes the next agent think they are
part of the project.

Removed by default:
  - throwaway probe scripts      scripts/testing/_*.py, _*.gd, tmp_*, *_probe.*
  - Godot import sidecars        *.png.import, *.import for assets that are gone
  - the isolated QA profile      <profile>/ (outside the repo)
  - Python bytecode              __pycache__/, *.pyc

Removed with --all:
  - captured screenshots         screenshots/debug/*.png
  - scene manifests              screenshots/debug/scene_manifest.json

Never removed: anything in core/tools/, tests/, or version-controlled files.

Usage:
    python game.py clean
    python game.py clean --all
    python game.py clean --all --keep-captures
    python game.py clean --dry-run
"""
import argparse
import fnmatch
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent.parent

# Never touch these, even with --all.
PROTECTED_DIRS = {"core", "tests", ".git", ".godot", "addons", "tools",
                  "node_modules", "__pycache__", ".agents"}

SCRATCH_PATTERNS = [
    "_*.py", "_*.gd", "_*.json",
    "tmp_*.py", "tmp_*.gd",
    "*_probe.py", "*_probe.gd",
    "*_debug.gd", "*_debug.py",
    "scratch_*.gd", "scratch_*.py",
]

CAPTURE_DIRS = ["screenshots/debug", "screenshots", "tests/screenshots"]
CAPTURE_FILES = ["scene_manifest.json", "*.png", "*.webp", "*.jpg"]
MANIFEST_NAMES = {"scene_manifest.json"}

removed, freed, skipped = 0, 0, 0
SEEN = set()


def is_protected(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    return bool(PROTECTED_DIRS.intersection(rel.parts[:-1]))


def is_tracked(path: Path) -> bool:
    """A tracked file is project content, not a byproduct. Never delete it."""
    try:
        p = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)],
                           cwd=str(PROJECT_ROOT), capture_output=True, timeout=15)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def remove(path: Path, dry: bool) -> None:
    global removed, freed
    if not path.exists():
        return
    key = str(path.resolve())
    if key in SEEN:
        return
    SEEN.add(key)
    if is_protected(path) or is_tracked(path):
        return
    try:
        size = path.stat().st_size if path.is_file() else sum(
            f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        size = 0
    if not dry:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError as exc:
            print(f"  could not remove {path.name}: {exc}")
            return
    removed += 1
    freed += size
    label = "would remove" if dry else "removed"
    print(f"  {label}: {path.relative_to(PROJECT_ROOT)}")


def sweep_scripts(dry: bool) -> None:
    print("Scratch scripts:")
    found = False
    for pattern in SCRATCH_PATTERNS:
        for p in PROJECT_ROOT.rglob(pattern):
            if not p.is_file() or p.suffix not in (".py", ".gd", ".json"):
                continue
            rel_parts = p.relative_to(PROJECT_ROOT).parts
            if PROTECTED_DIRS.intersection(rel_parts):
                continue
            found = True
            remove(p, dry)
    if not found:
        print("  none")


def sweep_caches(dry: bool) -> None:
    print("Caches and bytecode:")
    found = False
    for p in PROJECT_ROOT.rglob("__pycache__"):
        if p.is_dir() and ".git" not in p.parts:
            found = True
            remove(p, dry)
    for p in PROJECT_ROOT.rglob("*.pyc"):
        found = True
        remove(p, dry)
    if not found:
        print("  none")


def sweep_imports(dry: bool) -> None:
    """A .import file whose source asset is gone is dead weight."""
    print("Orphan .import sidecars:")
    found = False
    for p in PROJECT_ROOT.rglob("*.import"):
        source = Path(str(p)[: -len(".import")])
        if source.exists():
            continue
        if ".godot" in p.parts or ".git" in p.parts:
            continue
        found = True
        remove(p, dry)
    if not found:
        print("  none")


def sweep_profile(dry: bool) -> None:
    """The isolated APPDATA QA profile lives in LOCALAPPDATA, not the repo."""
    import os
    base = Path(os.environ.get("LOCALAPPDATA",
                Path.home() / "AppData" / "Local")) / "godot_dynamic_harness_profile"
    print("Isolated QA profile:")
    if base.is_dir():
        size = sum(f.stat().st_size for f in base.rglob("*") if f.is_file())
        if not dry:
            shutil.rmtree(base, ignore_errors=True)
        print(f"  {'would remove' if dry else 'removed'}: {base} ({size // 1024} KB)")
    else:
        print("  none")


def sweep_captures(all_mode: bool, keep_captures: bool, dry: bool) -> None:
    print("Captures and manifests:")
    found = False
    for rel in CAPTURE_DIRS:
        d = PROJECT_ROOT / rel
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            is_image = p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
            if keep_captures and is_image:
                continue
            # Only ever remove captures: PNG/WebP/JPEG plus known manifests.
            if not is_image and p.name not in MANIFEST_NAMES:
                continue
            found = True
            remove(p, dry)
        # Drop the directory itself if --all emptied it.
        if all_mode and not keep_captures and d.is_dir():
            try:
                empty = not any(d.iterdir())
            except OSError:
                empty = False
            if empty:
                if not dry:
                    shutil.rmtree(d, ignore_errors=True)
                print(f"  {'would remove' if dry else 'removed'}: {rel}/")
    if not found:
        print("  none")


def main() -> int:
    ap = argparse.ArgumentParser(description="Remove QA byproducts")
    ap.add_argument("--all", action="store_true", help="also delete captures and manifests")
    ap.add_argument("--keep-captures", action="store_true", help="keep PNGs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print(f"Cleanup{' (dry run)' if args.dry_run else ''} - {PROJECT_ROOT.name}")
    print("=" * 60)

    sweep_scripts(args.dry_run)
    sweep_imports(args.dry_run)
    sweep_caches(args.dry_run)
    sweep_profile(args.dry_run)
    if args.all:
        sweep_captures(True, args.keep_captures, args.dry_run)
    elif args.keep_captures:
        print("\nCaptures kept (pass --all to remove them).")

    print("\n" + "-" * 60)
    verb = "Would free" if args.dry_run else "Freed"
    print(f"{verb} {freed / 1024:.1f} KB across {removed} file(s)/dir(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())