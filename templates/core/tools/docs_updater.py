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

# Paths
TOOLS_DIR = Path(__file__).resolve().parent
JSON_LOG = TOOLS_DIR / "gdscript_version_changes.json"

def load_changes() -> dict:
    if not JSON_LOG.exists():
        print(f"Error: {JSON_LOG.name} not found.")
        sys.exit(1)
    with open(JSON_LOG, "r", encoding="utf-8") as f:
        return json.load(f)

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
        print("Note: Always use first-class signals and typed variables in Godot 4+.")

def cmd_scan(args):
    """Scan a .gd file for deprecated Godot 3.x syntax."""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    data = load_changes()
    patterns = []
    
    # Build list of deprecation checks
    for migration in data.get("version_migrations", []):
        if migration["to_version"].startswith("4"):
            for change in migration.get("changes", []):
                old_syn = change["old"]
                # Create a simple regex for the old syntax
                # E.g. "export var" -> r"\bexport\s+var\b"
                if old_syn == "export var":
                    patterns.append((r"(?<!@)\bexport\s+var\b", change))
                elif old_syn == "onready var":
                    patterns.append((r"(?<!@)\bonready\s+var\b", change))
                elif old_syn == "change_scene":
                    patterns.append((r"\bchange_scene\(", change))
                elif old_syn == "rand_range":
                    patterns.append((r"\brand_range\(", change))
                elif old_syn == "File.new()":
                    patterns.append((r"\bFile\.new\(", change))
                elif old_syn == "Directory.new()":
                    patterns.append((r"\bDirectory\.new\(", change))
                elif old_syn == "OS.get_unix_time()":
                    patterns.append((r"\bOS\.get_unix_time\(", change))
                elif old_syn == ".instance()":
                    patterns.append((r"\.instance\(", change))
                elif "yield(" in old_syn:
                    patterns.append((r"\byield\(", change))

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    
    issues = 0
    for i, line in enumerate(lines, start=1):
        # Ignore comments
        clean_line = line.split("#")[0]
        
        for pat, change in patterns:
            if re.search(pat, clean_line):
                issues += 1
                print(f"[{file_path.name}:{i}] Warning: Found deprecated syntax '{change['old']}'")
                print(f"    -> Use: {change['new']}")
                print(f"    -> Context: {change['context']}\n")

    if issues == 0:
        print(f"✅ {file_path.name} looks clean! No known Godot 3.x syntax found.")
    else:
        print(f"❌ Found {issues} outdated syntax issues in {file_path.name}. Please update to Godot 4.x standards.")
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

    args = parser.parse_args()
    
    if args.command == "query":
        cmd_query(args)
    elif args.command == "scan":
        cmd_scan(args)

if __name__ == "__main__":
    main()
