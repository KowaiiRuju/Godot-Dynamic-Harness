#!/usr/bin/env python3
"""Headless UI baseline inspection and mathematical regression diff engine."""
import json
import math
from pathlib import Path


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes_by_path = {}
    nodes_raw = data.get("nodes", [])
    if isinstance(nodes_raw, dict):
        nodes_by_path = nodes_raw
        raw_list = list(nodes_raw.values())
    else:
        for node in nodes_raw:
            nodes_by_path[node["path"]] = node
        raw_list = nodes_raw
    return {
        "scene": data.get("scene", ""),
        "viewport": data.get("viewport", []),
        "nodes": nodes_by_path,
        "raw_nodes": raw_list
    }


def save_baseline(manifest_path: Path, baseline_path: Path) -> dict:
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = load_manifest(manifest_path)
    baseline_path.write_text(json.dumps(loaded, indent=2) + "\n", encoding="utf-8")
    return loaded


def diff_baselines(baseline_path: Path, current_manifest_path: Path, tolerance: float = 1.0) -> list:
    base = load_manifest(baseline_path)
    curr = load_manifest(current_manifest_path)
    findings = []

    base_nodes = base["nodes"]
    curr_nodes = curr["nodes"]

    all_paths = sorted(set(base_nodes.keys()).union(set(curr_nodes.keys())))

    for path in all_paths:
        if path not in curr_nodes:
            findings.append({
                "code": "BASELINE_NODE_MISSING",
                "message": f"Node in baseline is missing from current layout: {path}",
                "path": path,
                "fix_hint": "Check if node was renamed or removed intentionally."
            })
            continue
        if path not in base_nodes:
            findings.append({
                "code": "BASELINE_NODE_ADDED",
                "message": f"Unexpected new node present in layout: {path}",
                "path": path,
                "fix_hint": "Save new baseline if addition is intentional: python game.py baseline --save"
            })
            continue

        b_node = base_nodes[path]
        c_node = curr_nodes[path]

        # Check rect differences
        b_rect = b_node.get("rect", [0, 0, 0, 0])
        c_rect = c_node.get("rect", [0, 0, 0, 0])
        deltas = [c_rect[i] - b_rect[i] for i in range(4)]
        if any(abs(d) > tolerance for d in deltas):
            findings.append({
                "code": "BASELINE_RECT_CHANGED",
                "message": f"Node bounds shifted [dx={deltas[0]:.1f}, dy={deltas[1]:.1f}, dw={deltas[2]:.1f}, dh={deltas[3]:.1f}] exceeding tolerance {tolerance}px: {path}",
                "path": path,
                "baseline_rect": b_rect,
                "current_rect": c_rect,
                "fix_hint": "Check anchors, margins, or container layout; or save updated baseline."
            })

        # Check text differences
        if b_node.get("text") != c_node.get("text") and "text" in b_node:
            findings.append({
                "code": "BASELINE_TEXT_CHANGED",
                "message": f"Text changed from '{b_node.get('text')}' to '{c_node.get('text')}': {path}",
                "path": path,
                "fix_hint": "Verify text update or save baseline."
            })

        # Check font size
        if b_node.get("font_size") != c_node.get("font_size") and "font_size" in b_node:
            findings.append({
                "code": "BASELINE_FONT_CHANGED",
                "message": f"Font size changed from {b_node.get('font_size')} to {c_node.get('font_size')}: {path}",
                "path": path,
                "fix_hint": "Verify font size change in Theme or node properties."
            })

        # Check mouse filter
        if b_node.get("mouse_filter") != c_node.get("mouse_filter") and "mouse_filter" in b_node:
            findings.append({
                "code": "BASELINE_MOUSE_FILTER_CHANGED",
                "message": f"mouse_filter changed from {b_node.get('mouse_filter')} to {c_node.get('mouse_filter')}: {path}",
                "path": path,
                "fix_hint": "Check if mouse input propagation was altered intentionally."
            })

    return findings
