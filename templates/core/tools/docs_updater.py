#!/usr/bin/env python3
"""
docs_updater.py - Godot Documentation & GDScript Version Syntax Checker

This tool helps AI agents and developers ensure they are using updated Godot 4.7+
documentation and syntax, rather than relying on outdated preset scripts (Godot 3.x).

It reads from `gdscript_version_changes.json` and can scan a .gd file to warn 
about deprecated syntax.
"""

import sys
import json
import re
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Paths
TOOLS_DIR = Path(__file__).resolve().parent
JSON_LOG = TOOLS_DIR / "gdscript_version_changes.json"

def load_changes() -> dict:
    if not JSON_LOG.exists():
        print(f"Error: {JSON_LOG.name} not found.")
        sys.exit(1)
    with open(JSON_LOG, "r", encoding="utf-8") as f:
        return json.load(f)

def save_changes(data: dict):
    with open(JSON_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def cmd_query(args):
    """Query the JSON log for a specific keyword to check if it's deprecated."""
    data = load_changes()
    keyword = args.keyword.lower()
    
    found = False
    for migration in data.get("version_migrations", []):
        for change in migration.get("changes", []):
            if keyword in change["old"].lower() or keyword in change["new"].lower():
                found = True
                print(f"\nMigration: {migration['from_version']} -> {migration['to_version']}")
                print(f"  Type:    {change.get('type')}")
                print(f"  Old:     {change.get('old')}")
                print(f"  New:     {change.get('new')}")
                print(f"  Context: {change.get('context')}")
                
    if not found:
        print(f"No deprecation or syntax change found for '{keyword}' in the log.")
        
    print("\n--- Godot 4.x Engine Best Practices ---")
    best_practices = data.get("engine_best_practices", {})
    for k, v in best_practices.items():
        print(f"[{k.upper()}]: {v}")

def cmd_scan(args):
    """Scan a .gd file for deprecated Godot 3.x syntax."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    data = load_changes()
    patterns = []
    seen_old = set()

    # Build list of deprecation checks
    for migration in data.get("version_migrations", []):
        if not migration.get("to_version", "").startswith("4"):
            continue
        for change in migration.get("changes", []):
            old_syn = change.get("old", "")
            if not old_syn or old_syn in seen_old:
                continue
            seen_old.add(old_syn)
            pat = _compile_pattern(old_syn)
            if pat:
                patterns.append((pat, change))

    if not patterns:
        print(f"Note: no mappable deprecation patterns in {JSON_LOG.name}; "
              f"nothing to check. Use --learn-syntax-old to add one.")
        return

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print(f"Error: cannot read '{file_path}': {exc}")
        sys.exit(1)
    lines = content.splitlines()

    issues = 0
    for i, line in enumerate(lines, start=1):
        clean_line = _strip_comment(line)
        if not clean_line.strip():
            continue
        for pat, change in patterns:
            if pat.search(clean_line):
                issues += 1
                print(f"[{file_path.name}:{i}] deprecated '{change['old']}'")
                print(f"    -> use: {change['new']}")
                print(f"    -> {change.get('context', '')}\n")

    if issues == 0:
        print(f"OK {file_path.name}: no known deprecated syntax.")
    else:
        print(f"{issues} deprecated pattern(s) in {file_path.name}.")
        sys.exit(1)


def _strip_comment(line: str) -> str:
    """Drop # comments and quoted strings so prose in a comment cannot trigger."""
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


def _compile_pattern(old_syn: str):
    """Map a known Godot 3.x token to a regex, or None if it cannot be mapped.

    Returning None instead of silently skipping nothing matters: an unmapped
    entry would otherwise make the scanner report a clean file while checking
    nothing.
    """
    table = {
        "export var": r"(?<!@)\bexport\s+var\b",
        "export(int": r"(?<!@)\bexport\s*\(",
        "onready var": r"(?<!@)\bonready\s+var\b",
        "change_scene": r"\b(?:change_scene|change_scene_to|change_scene_by_path)\s*\(",
        "rand_range": r"\brand_range\s*\(",
        "File.new()": r"\bFile\.new\s*\(",
        "Directory.new()": r"\bDirectory\.new\s*\(",
        "OS.get_unix_time()": r"\bOS\.get_unix_time\s*\(",
        ".instance()": r"\.instance\s*\(",
        "KinematicBody": r"(?<![\w.])KinematicBody\w*\b",
        "Spatial": r"(?<![\w.])Spatial\b",
        "PoolVector": r"(?<![\w.])Pool\w*Array\b",
        "yield(": r"\byield\s*\(",
        "instance()": r"(?<![\w.])(?:get_node|load)\s*\([^)]*\)\.instance\s*\(",
        "connect(self, \"\": r"\bconnect\s*\(\s*self\s*,",
    }
    if old_syn in table:
        return re.compile(table[old_syn])
    if "yield(" in old_syn:
        return re.compile(r"\byield\s*\(")
    return None

def cmd_learn(args):
    """Dynamically append new context, syntax changes, or best practices to the JSON log."""
    data = load_changes()
    
    if args.practice_key and args.practice_desc:
        if "engine_best_practices" not in data:
            data["engine_best_practices"] = {}
        data["engine_best_practices"][args.practice_key] = args.practice_desc
        save_changes(data)
        print(f"✅ Learned new best practice: [{args.practice_key}] -> {args.practice_desc}")
    elif args.syntax_old and args.syntax_new:
        # Find or create a 'Dynamic Updates' migration block
        migration_block = None
        for m in data.get("version_migrations", []):
            if m.get("from_version") == "Dynamic":
                migration_block = m
                break
        if not migration_block:
            migration_block = {"from_version": "Dynamic", "to_version": "Latest", "changes": []}
            data.setdefault("version_migrations", []).append(migration_block)
            
        new_change = {
            "old": args.syntax_old,
            "new": args.syntax_new,
            "type": "learned",
            "context": args.syntax_context or "Dynamically learned during project development."
        }
        migration_block["changes"].append(new_change)
        save_changes(data)
        print(f"✅ Learned new syntax update: '{args.syntax_old}' -> '{args.syntax_new}'")
    else:
        print("❌ Invalid learn arguments. Provide either practice arguments or syntax arguments.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="GDScript Syntax Docs Checker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Query
    p_query = subparsers.add_parser("query", help="Search the syntax log for a keyword")
    p_query.add_argument("keyword", help="The Godot function/keyword to search (e.g. 'export')")
    
    # Scan
    p_scan = subparsers.add_parser("scan", help="Scan a .gd script for deprecated syntax")
    p_scan.add_argument("file", help="Path to the .gd file to scan")

    # Learn
    p_learn = subparsers.add_parser("learn", help="Add new context to the knowledge base")
    p_learn.add_argument("--practice-key", help="Key name for the new best practice")
    p_learn.add_argument("--practice-desc", help="Description of the best practice")
    p_learn.add_argument("--syntax-old", help="Old deprecated syntax")
    p_learn.add_argument("--syntax-new", help="New correct syntax")
    p_learn.add_argument("--syntax-context", help="Context for the syntax change")

    args = parser.parse_args()
    
    if args.command == "query":
        cmd_query(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "learn":
        cmd_learn(args)

if __name__ == "__main__":
    main()
