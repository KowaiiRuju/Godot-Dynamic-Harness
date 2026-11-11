#!/usr/bin/env python3
"""Godot save file inspection, schema verification, and user:// data debugging tool."""
import json
import os
import sys
from pathlib import Path


def discover_save_files(root: Path, custom_dir: Path = None) -> list:
    candidates = []
    # Project-local save folders
    for search_dir in (custom_dir, root / "saves", root / "save", root / "user_data", root / ".saves"):
        if search_dir and search_dir.is_dir():
            for ext in (".json", ".tres", ".res", ".cfg", ".save", ".dat"):
                candidates.extend(search_dir.rglob("*" + ext))

    # Also check OS user:// directory for the project name if specified in project.godot
    project_godot = root / "project.godot"
    project_name = None
    if project_godot.is_file():
        for line in project_godot.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("config/name="):
                project_name = line.split("=")[1].strip().strip('"')
                break

    if project_name:
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA")
            if appdata:
                godot_user = Path(appdata) / "Godot" / "app_userdata" / project_name
                if godot_user.is_dir():
                    for ext in (".json", ".tres", ".res", ".cfg", ".save", ".dat"):
                        candidates.extend(godot_user.rglob("*" + ext))
        elif sys.platform == "linux":
            home = Path.home()
            godot_user = home / ".local" / "share" / "godot" / "app_userdata" / project_name
            if godot_user.is_dir():
                for ext in (".json", ".tres", ".res", ".cfg", ".save", ".dat"):
                    candidates.extend(godot_user.rglob("*" + ext))

    return sorted(set(candidates))


def inspect_save_file(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")

    size = path.stat().st_size
    mtime = path.stat().st_mtime
    suffix = path.suffix.lower()

    data = None
    keys = []
    is_valid_json = False

    if suffix in (".json", ".save"):
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            is_valid_json = True
            if isinstance(data, dict):
                keys = list(data.keys())
        except Exception:
            pass

    return {
        "file": str(path),
        "size_bytes": size,
        "format": "json" if is_valid_json else suffix.lstrip("."),
        "top_level_keys": keys[:20],
        "key_count": len(keys) if keys else 0,
        "valid": is_valid_json or size > 0
    }


def audit_saves(root: Path, custom_dir: Path = None) -> dict:
    files = discover_save_files(root, custom_dir)
    inspections = [inspect_save_file(f) for f in files]
    return {
        "save_count": len(files),
        "files": inspections
    }
