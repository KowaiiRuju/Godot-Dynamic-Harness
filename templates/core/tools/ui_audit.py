#!/usr/bin/env python3
"""
ui_audit.py - Read scene_manifest.json and flag layout defects a screenshot hides.

A PNG shows you that something looks wrong. This shows you *why*: controls
pushed outside the viewport, labels too small to read, interactive nodes with
mouse_filter = IGNORE, or text that overflows its box.

Usage:
    python core/tools/ui_audit.py
    python core/tools/ui_audit.py screenshots/debug/scene_manifest.json
    python core/tools/ui_audit.py --min-font 12 --viewport 1280x720
"""
import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent.parent
DEFAULT_MANIFEST = PROJECT_ROOT / "screenshots" / "debug" / "scene_manifest.json"

# mouse_filter values in Godot 4
MOUSE_STOP, MOUSE_PASS, MOUSE_IGNORE = 0, 1, 2
# Godot emits a String for mouse_filter when it differs from the default.
INTERACTIVE = {"Button", "LineEdit", "TextEdit", "TextureButton", "CheckBox",
               "OptionButton", "HSlider", "VSlider", "SpinBox", "ItemList",
               "Tree", "RichTextLabel"}


def load(path: Path):
    if not path.is_file():
        print(f"Error: no manifest at {path}")
        print("Run `python game.py capture --scene res://<scene>.tscn` first.")
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit a scene manifest for layout defects")
    ap.add_argument("manifest", nargs="?", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--min-font", type=int, default=10,
                    help="flag text smaller than this (default 10)")
    ap.add_argument("--viewport", default="", help="WxH; defaults to the manifest's own size")
    ap.add_argument("--tolerance", type=int, default=2,
                    help="px of slack before calling something offscreen")
    args = ap.parse_args()

    data = load(Path(args.manifest))
    nodes = data if isinstance(data, list) else data.get("controls", [])

    vp = None
    if args.viewport:
        try:
            w, h = args.viewport.lower().split("x")
            vp = (float(w), float(h))
        except ValueError:
            print("Error: --viewport must look like 1280x720")
            sys.exit(1)
    elif isinstance(data, dict):
        size = data.get("viewport_size")
        if size and len(size) == 2:
            vp = (float(size[0]), float(size[1]))

    findings = []
    for n in nodes:
        name = n.get("name", "?")
        rect = n.get("rect") or [0, 0, 0, 0]
        x, y, w, h = (float(v) for v in rect[:4])
        ntype = n.get("type", "")

        if vp:
            vw, vh = vp
            if w > 0 and h > 0:
                if x < -args.tolerance or y < -args.tolerance:
                    findings.append(("offscreen-topleft", name,
                                     f"top-left ({x:.0f},{y:.0f}) is outside 0,0"))
                if x + w > vw + args.tolerance or y + h > vh + args.tolerance:
                    findings.append(("offscreen-bottomright", name,
                                     f"bottom-right ({x + w:.0f},{y + h:.0f}) "
                                     f"exceeds viewport {vw:.0f}x{vh:.0f}"))
            if w <= 0 or h <= 0:
                findings.append(("zero-size", name, f"size is {w:.0f}x{h:.0f}"))

        font = n.get("font_size")
        if isinstance(font, int) and 0 < font < args.min_font:
            findings.append(("tiny-text", name, f"font_size={font} < {args.min_font}"))

        mf = n.get("mouse_filter")
        if ntype in INTERACTIVE and mf in (2, "2", "Ignore", MOUSE_IGNORE):
            findings.append(("dead-control", name,
                             f"{ntype} has mouse_filter=IGNORE and cannot be clicked"))

        text = n.get("text") or ""
        if text and w > 0 and h > 0 and len(text) * (font or 10) * 0.5 > w * 3:
            findings.append(("text-overflow", name,
                             f"{len(text)} chars in a {w:.0f}px wide box"))

    if not nodes:
        print("Manifest contains no control records.")
        return 0

    print(f"Auditing {len(nodes)} controls"
          f"{f' against {vp[0]:.0f}x{vp[1]:.0f}' if vp else ''}...\n")

    if not findings:
        print("PASS: no layout defects detected.")
        return 0

    by_kind = {}
    for kind, name, msg in findings:
        by_kind.setdefault(kind, []).append((name, msg))
    for kind in sorted(by_kind):
        group = by_kind[kind]
        print(f"--- {kind} ({len(group)}) ---")
        for name, msg in group[:15]:
            print(f"  {name}: {msg}")
        if len(group) > 15:
            print(f"  ... and {len(group) - 15} more")
        print()
    print(f"FAIL: {len(findings)} layout defect(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
