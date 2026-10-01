#!/usr/bin/env python3
"""
tscn_lint.py - Static integrity checker for Godot .tscn / .tres scene files.

Catches the failure modes that make a scene silently fail to load, without
needing to boot the engine. Every check here corresponds to a real crash or
blank-screen cause.

Usage:
    python core/tools/tscn_lint.py                      # lint whole project
    python core/tools/tscn_lint.py scenes/ entities/    # lint specific dirs
    python core/tools/tscn_lint.py --json               # machine-readable
"""
import base64
import binascii
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent.parent

SKIP_DIRS = {".godot", ".git", "builds", "__pycache__", "graphify-out", ".agents"}

GD_SCENE_FORMAT = re.compile(r'^\[gd_scene\s+format=(\d+)\]')
EXT_RESOURCE = re.compile(r'\[ext_resource\s+type="([^"]+)"(?:\s+uid="[^"]*")?\s+path="([^"]+)"\s+id="([^"]+)"')
SUB_RESOURCE = re.compile(r'\[sub_resource\s+type="([^"]+)"(?:\s+id="([^"]+)")?')
EXT_USE = re.compile(r'ExtResource\("([^"]+)"\)')
PACKED_BYTEARRAY = re.compile(r'PackedByteArray\("([^"]*)"\)')
NODE_TAG = re.compile(r'^\[node\s+name="([^"]*)"')
# Godot 4 resource format version. 3 is current; 4+ is rejected by the parser.
MAX_GD_FORMAT = 3


class Issue:
    __slots__ = ("path", "line", "kind", "message")

    def __init__(self, path: Path, line: int, kind: str, message: str):
        self.path, self.line, self.kind, self.message = path, line, kind, message

    def __str__(self):
        return f"{self.path}:{self.line}  [{self.kind}] {self.message}"


def collect_targets(paths):
    roots = [PROJECT_ROOT] if not paths else [
        (Path(p) if Path(p).is_absolute() else PROJECT_ROOT / p) for p in paths]
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            for pat in ("*.tscn", "*.tres"):
                files.extend(root.rglob(pat))
    return sorted({f.resolve() for f in files if not SKIP_DIRS.intersection(f.parts)})


def check_format(lines, path, issues):
    """format=4 or higher makes the whole file unparseable."""
    m = GD_SCENE_FORMAT.match(lines[0] if lines else "")
    if m:
        version = int(m.group(1))
        if version > MAX_GD_FORMAT:
            issues.append(Issue(path, 1, "bad-format",
                                f"format={version} is not supported by this engine "
                                f"(max {MAX_GD_FORMAT}); the entire scene fails to load"))


def check_ext_resources(lines, path, issues):
    """Every ExtResource() must have a matching [ext_resource] declaration."""
    declared, used = {}, set()
    for n, line in enumerate(lines, start=1):
        m = EXT_RESOURCE.match(line)
        if m:
            declared[m.group(3)] = (m.group(1), m.group(2), n)
    for n, line in enumerate(lines, start=1):
        used.update(EXT_USE.findall(line))
    for rid in sorted(used - set(declared)):
        issues.append(Issue(path, n, "undeclared-ext",
                            f'ExtResource("{rid}") has no [ext_resource] declaration'))
    for rid, (rtype, res_path, n) in declared.items():
        if rid not in used:
            issues.append(Issue(path, n, "unused-ext",
                                f'ext_resource "{rid}" ({res_path}) is declared but unused'))
        if not res_path.startswith("res://"):
            continue
        if not (PROJECT_ROOT / res_path[6:]).exists():
            issues.append(Issue(path, n, "missing-target",
                                f"{rtype} not found on disk: {res_path}"))


def check_packed_bytearray(lines, path, issues):
    """Truncated base64 in tile_map_data / mesh data is a silent scene killer."""
    for n, line in enumerate(lines, start=1):
        for payload in PACKED_BYTEARRAY.findall(line):
            if not payload:
                continue
            if len(payload) % 4 != 0:
                issues.append(Issue(
                    path, n, "bad-base64",
                    f"PackedByteArray length {len(payload)} is not a multiple of 4 "
                    f"(remainder {len(payload) % 4}); data is truncated or corrupt"))
                continue
            try:
                base64.b64decode(payload, validate=True)
            except (binascii.Error, ValueError) as exc:
                issues.append(Issue(path, n, "bad-base64",
                                    f"PackedByteArray is not valid base64: {exc}"))


def check_structure(lines, path, issues):
    """Structural sanity: stray ExtResource() and duplicated node names."""
    names, seen = [], set()
    for n, line in enumerate(lines, start=1):
        m = NODE_TAG.match(line)
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            issues.append(Issue(path, n, "dup-node",
                                f'duplicate node name "{name}" in the same parent'))
        seen.add(name)
        names.append(name)
    if names and not any(n.startswith("[gd_scene") for n in [lines[0]] if lines):
        issues.append(Issue(path, 1, "no-header", "file has no [gd_scene] header"))


def lint_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [Issue(path, 0, "unreadable", str(exc))]
    lines = text.splitlines()
    issues = []
    check_format(lines, path, issues)
    check_ext_resources(lines, path, issues)
    check_packed_bytearray(lines, path, issues)
    check_structure(lines, path, issues)
    return issues


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv

    targets = collect_targets(args)
    if not targets:
        print("No .tscn / .tres files found.")
        return 0

    all_issues = []
    for f in targets:
        all_issues.extend(lint_file(f))

    if as_json:
        print(json.dumps(
            [{"file": rel(i.path), "line": i.line, "kind": i.kind, "message": i.message}
             for i in all_issues], indent=2))
        return 1 if all_issues else 0

    print(f"Linting {len(targets)} scene/resource files...\n")
    by_kind = {}
    for i in all_issues:
        by_kind.setdefault(i.kind, []).append(i)
    for kind in sorted(by_kind):
        group = by_kind[kind]
        print(f"--- {kind} ({len(group)}) ---")
        for i in group[:20]:
            print(f"  {rel(i.path)}:{i.line}  {i.message}")
        if len(group) > 20:
            print(f"  ... and {len(group) - 20} more")
        print()

    if all_issues:
        print(f"FAIL: {len(all_issues)} issue(s) across {len(by_kind)} category(ies).")
        return 1
    print("PASS: all scene files are structurally valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
