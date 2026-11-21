#!/usr/bin/env python3
"""Deterministic style-agnostic UI grader against dissection_manifest.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "project.godot").is_file() or (parent / "game.py").is_file():
            return parent
    return here.parents[3] if len(here.parents) > 3 else here.parent


REPO_ROOT = _resolve_repo_root()


def _rects_intersect(a: Dict[str, float], b: Dict[str, float]) -> bool:
    if a.get("w", 0) <= 0 or a.get("h", 0) <= 0 or b.get("w", 0) <= 0 or b.get("h", 0) <= 0:
        return False
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )


def _infer_root_from_manifest(manifest_path: Path) -> Path:
    for parent in manifest_path.resolve().parents:
        if (parent / "project.godot").is_file() or (parent / "game.py").is_file():
            return parent
    # If manifest is at <root>/artifacts/ui_pipeline/dissection_manifest.json -> parents[2]
    if len(manifest_path.resolve().parents) >= 3:
        return manifest_path.resolve().parents[2]
    return REPO_ROOT


def _load_borders_manifest_margins(root: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """Load exact per-side texture_margin expectations from borders_manifest.json if present."""
    base = root or REPO_ROOT
    candidates = [
        base / "assets" / "ui" / "kit_v2" / "borders_manifest.json",
        base / "assets" / "ui" / "borders_manifest.json",
        REPO_ROOT / "assets" / "ui" / "kit_v2" / "borders_manifest.json",
    ]
    manifest_file = next((c for c in candidates if c.is_file()), None)
    if manifest_file is None:
        return {}
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    margins_by_res: Dict[str, Dict[str, float]] = {}
    for entry in data.get("assets", []):
        res_path = entry.get("res_path")
        tm = entry.get("texture_margin")
        if isinstance(res_path, str) and isinstance(tm, dict):
            margins_by_res[res_path] = {
                side: float(tm.get(side, 0.0)) for side in ("left", "top", "right", "bottom")
            }
    return margins_by_res


def _parent_path(node_path: str) -> str:
    if "/" not in node_path:
        return "."
    return node_path.rsplit("/", 1)[0]


def _is_fullscreen_backdrop(rect: Dict[str, float], viewport: List[int]) -> bool:
    vw = float(viewport[0]) if len(viewport) > 0 and viewport[0] > 0 else 1280.0
    vh = float(viewport[1]) if len(viewport) > 1 and viewport[1] > 0 else 720.0
    return rect.get("w", 0.0) >= vw * 0.9 and rect.get("h", 0.0) >= vh * 0.9


def _is_slot_control(ctrl: Dict[str, Any]) -> bool:
    path = str(ctrl.get("path", ""))
    name = str(ctrl.get("name", "")).lower()
    return ("HotbarContainer/" in path or "slot" in name) and ctrl.get("class") == "PanelContainer"


def grade_dissection(manifest_path: str | Path, tolerance_px: float = 2.0) -> Dict[str, Any]:
    """Evaluate deterministic UI layout & StyleBox rules across all styled_controls and key_components."""
    path = Path(manifest_path)
    if not path.is_file():
        return {
            "schema_version": 2,
            "cmd": "mockup-grade",
            "status": "failed",
            "passed": False,
            "failed_count": 1,
            "failed_components": [{
                "component": "manifest",
                "rule": "MISSING_MANIFEST",
                "message": f"Dissection manifest not found: {path.as_posix()}",
                "fix": "Run python game.py mockup-dissect first",
            }],
            "next_command": "python game.py mockup-dissect --json --compact",
            "pipeline_connection": {
                "current_stage": "stage_3_grade",
                "next_command": "python game.py mockup-dissect --json --compact",
                "next_stage": "stage_1_dissect",
            },
        }

    manifest = json.loads(path.read_text(encoding="utf-8"))
    root = _infer_root_from_manifest(path)
    scene_posix = str(manifest.get("scene", "modals/game_ui.tscn")).replace("\\", "/")
    layers = manifest.get("measured_layers_px", {})
    kit_margins = _load_borders_manifest_margins(root)
    req_patch = 15.0 if kit_margins else float(layers.get("required_patch_margin_px", 31))
    min_content = 12.0
    key_comp = manifest.get("key_components", {})
    controls: List[Dict[str, Any]] = manifest.get("controls", [])
    raw_styled = manifest.get("styled_controls", [])
    viewport = manifest.get("viewport", [1280, 720])
    probe_mode = manifest.get("probe_mode", "unknown")

    styled_list: List[Dict[str, Any]] = []
    if isinstance(raw_styled, dict):
        styled_list = [v for v in raw_styled.values() if isinstance(v, dict)]
    elif isinstance(raw_styled, list):
        styled_list = [v for v in raw_styled if isinstance(v, dict)]
    if not styled_list:
        styled_list = [c for c in controls if isinstance(c.get("styles"), dict) and c.get("styles")]

    failed: List[Dict[str, Any]] = []
    graded_paths: set[str] = set()

    def grade_control_styles(comp_label: str, ctrl: Dict[str, Any]) -> None:
        if _is_slot_control(ctrl):
            return
        if ctrl.get("class") == "ProgressBar":
            return
        styles = ctrl.get("styles", {})
        if not isinstance(styles, dict):
            return
        for _sname, sb in styles.items():
            if not isinstance(sb, dict):
                continue
            stype = sb.get("type", "")
            if stype == "StyleBoxTexture":
                margins = {
                    side: float(sb.get(f"patch_margin_{side}", 0.0))
                    for side in ("left", "top", "right", "bottom")
                }
                expected_margins = kit_margins.get(
                    sb.get("texture", ""),
                    {side: req_patch for side in ("left", "top", "right", "bottom")},
                )
                bad_sides = {
                    s: v for s, v in margins.items() if abs(v - expected_margins[s]) > tolerance_px
                }
                if bad_sides:
                    failed.append({
                        "component": comp_label,
                        "node_path": ctrl.get("path"),
                        "rule": "BEZEL_PATCH_MARGIN_MISMATCH",
                        "expected_px": expected_margins,
                        "actual": bad_sides,
                        "fix": f"Set patch_margin_* (texture_margin_*) to {expected_margins} (+/- {int(tolerance_px)}px)",
                    })
            elif stype == "StyleBoxFlat":
                borders = {
                    side: float(sb.get(f"border_width_{side}", 0.0))
                    for side in ("left", "top", "right", "bottom")
                }
                bad_borders = {s: v for s, v in borders.items() if abs(v - req_patch) > tolerance_px}
                if bad_borders:
                    failed.append({
                        "component": comp_label,
                        "node_path": ctrl.get("path"),
                        "rule": "BORDER_WIDTH_MISMATCH",
                        "expected_px": req_patch,
                        "actual": bad_borders,
                        "fix": f"Set border_width_* to {int(req_patch)}px (+/- {int(tolerance_px)}px)",
                    })

            if stype in ("StyleBoxTexture", "StyleBoxFlat"):
                content_margins = {
                    side: float(sb.get(f"content_margin_{side}", 0.0))
                    for side in ("left", "top", "right", "bottom")
                }
                if any(v >= 0 and v < min_content for v in content_margins.values()):
                    failed.append({
                        "component": comp_label,
                        "node_path": ctrl.get("path"),
                        "rule": "CONTENT_MARGIN_TOO_SMALL",
                        "min_px": min_content,
                        "actual": content_margins,
                        "fix": f"Set StyleBox content_margin_* >= {int(min_content)}px so inner content does not crowd the bezel frame",
                    })

    # 1a. Grade named key components first (preserving legacy component IDs when present)
    hd_panel_keys = (
        "HD01_TopLeftPanel",
        "HD02_ProfileCard",
        "HD03_MiniCalendarWidget",
        "HD04_QuestPanel",
        "HD05_HotbarWrapper",
    )
    for k in hd_panel_keys:
        ctrl = key_comp.get(k)
        if not ctrl:
            continue
        node_key = str(ctrl.get("path") or ctrl.get("name") or k)
        graded_paths.add(node_key)
        grade_control_styles(k, ctrl)

    # 1b. Grade ALL remaining styled_controls dynamically across any scene
    for ctrl in styled_list:
        node_key = str(ctrl.get("path") or ctrl.get("name") or "")
        if not node_key or node_key in graded_paths:
            continue
        graded_paths.add(node_key)
        comp_label = str(ctrl.get("name") or node_key)
        grade_control_styles(comp_label, ctrl)

    # 2. Check ProgressBar start/end X alignment (both HD07/HD09 and any sibling/shared-parent ProgressBars)
    aligned_bar_pairs: set[Tuple[str, str]] = set()
    lvl_bar = key_comp.get("HD07_LevelProgressBar")
    en_bar = key_comp.get("HD09_EnergyProgressBar")
    if lvl_bar and en_bar:
        p1 = str(lvl_bar.get("path", "HD07"))
        p2 = str(en_bar.get("path", "HD09"))
        aligned_bar_pairs.add(tuple(sorted((p1, p2))))
        lr = lvl_bar.get("rect", {})
        er = en_bar.get("rect", {})
        if lr.get("w", 0) > 0 and er.get("w", 0) > 0:
            dx = abs(float(lr.get("x", 0)) - float(er.get("x", 0)))
            dw = abs(float(lr.get("w", 0)) - float(er.get("w", 0)))
            if dx > 1.0 or dw > 1.0:
                failed.append({
                    "component": "HD07_HD09_ProgressBarAlignment",
                    "nodes": [lvl_bar.get("path"), en_bar.get("path")],
                    "rule": "PROGRESS_BAR_X_MISALIGNED",
                    "level_bar_rect": lr,
                    "energy_bar_rect": er,
                    "fix": "Set uniform custom_minimum_size.x on sibling label columns so ProgressBar start/end X match within 1px",
                })

    progress_bars = [
        c for c in controls
        if c.get("class") == "ProgressBar"
        and c.get("visible", True)
        and c.get("rect", {}).get("w", 0) > 0
    ]
    bars_by_group: Dict[str, List[Dict[str, Any]]] = {}
    for pb in progress_bars:
        p_path = str(pb.get("path", ""))
        parent = _parent_path(p_path)
        grandparent = _parent_path(parent) if parent != "." else "."
        group_key = grandparent if grandparent != "." else parent
        bars_by_group.setdefault(group_key, []).append(pb)

    for group_key, group_bars in bars_by_group.items():
        if len(group_bars) < 2:
            continue
        base_bar = group_bars[0]
        br = base_bar.get("rect", {})
        for other_bar in group_bars[1:]:
            pair_key = tuple(sorted((str(base_bar.get("path", "")), str(other_bar.get("path", "")))))
            if pair_key in aligned_bar_pairs:
                continue
            aligned_bar_pairs.add(pair_key)
            orr = other_bar.get("rect", {})
            dx = abs(float(br.get("x", 0)) - float(orr.get("x", 0)))
            dw = abs(float(br.get("w", 0)) - float(orr.get("w", 0)))
            if dx > 1.0 or dw > 1.0:
                failed.append({
                    "component": f"ProgressBarAlignment:{base_bar.get('name')}_{other_bar.get('name')}",
                    "nodes": [base_bar.get("path"), other_bar.get("path")],
                    "rule": "PROGRESS_BAR_X_MISALIGNED",
                    "level_bar_rect": br,
                    "energy_bar_rect": orr,
                    "fix": "Align sibling ProgressBar start X and width within 1px inside shared container",
                })

    # 3. Check Single Outer Container for Profile + Calendar when both exist
    prof = key_comp.get("HD02_ProfileCard")
    cal = key_comp.get("HD03_MiniCalendarWidget")
    top_left = key_comp.get("HD01_TopLeftPanel")
    if prof and cal and not top_left:
        failed.append({
            "component": "HD01_TopLeftPanel",
            "rule": "MISSING_SINGLE_OUTER_CONTAINER",
            "fix": "Wrap ProfileCard and MiniCalendarWidget inside a single TopLeftPanel outer container",
        })

    # 4. Check Quest panel vs TopLeftPanel overlap AND general sibling container overlaps
    reported_overlaps: set[Tuple[str, str]] = set()
    quest = key_comp.get("HD04_QuestPanel")
    if quest and top_left:
        qr = quest.get("rect", {})
        tr = top_left.get("rect", {})
        if _rects_intersect(qr, tr):
            pair = tuple(sorted((str(quest.get("path", "")), str(top_left.get("path", "")))))
            reported_overlaps.add(pair)
            failed.append({
                "component": "HD04_QuestPanel",
                "node_path": quest.get("path"),
                "rule": "QUEST_OVERLAPS_TOP_LEFT",
                "quest_rect": qr,
                "top_left_rect": tr,
                "fix": "Anchor CampfireCompass/QuestPanel below TopLeftPanel so rects do not intersect",
            })

    siblings_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for ctrl in controls:
        if not ctrl.get("visible", True):
            continue
        r = ctrl.get("rect", {})
        if r.get("w", 0) <= 0 or r.get("h", 0) <= 0:
            continue
        if _is_fullscreen_backdrop(r, viewport):
            continue
        p_path = str(ctrl.get("path", ""))
        parent = _parent_path(p_path)
        siblings_by_parent.setdefault(parent, []).append(ctrl)

    for _parent, sibs in siblings_by_parent.items():
        if len(sibs) < 2:
            continue
        for i in range(len(sibs)):
            for j in range(i + 1, len(sibs)):
                a, b = sibs[i], sibs[j]
                pair = tuple(sorted((str(a.get("path", "")), str(b.get("path", "")))))
                if pair in reported_overlaps:
                    continue
                ra, rb = a.get("rect", {}), b.get("rect", {})
                if _rects_intersect(ra, rb):
                    reported_overlaps.add(pair)
                    failed.append({
                        "component": f"{a.get('name')}_vs_{b.get('name')}",
                        "node_path": a.get("path"),
                        "nodes": [a.get("path"), b.get("path")],
                        "rule": "SIBLING_CONTROL_OVERLAP",
                        "rect_a": ra,
                        "rect_b": rb,
                        "fix": f"Adjust anchors/offsets or container separation so sibling controls '{a.get('name')}' and '{b.get('name')}' do not overlap",
                    })

    # 5. Check Hotbar / item slot well padding (>= 6px inner margin around icons)
    hotbar_slots = [c for c in controls if _is_slot_control(c)]
    for slot in hotbar_slots:
        for _, sb in slot.get("styles", {}).items():
            cm = {s: float(sb.get(f"content_margin_{s}", 0.0)) for s in ("left", "top", "right", "bottom")}
            if any(v >= 0 and v < 6.0 for v in cm.values()):
                failed.append({
                    "component": f"HotbarSlot:{slot.get('name')}",
                    "node_path": slot.get("path"),
                    "rule": "HOTBAR_WELL_PADDING_TOO_SMALL",
                    "min_px": 6.0,
                    "actual": cm,
                    "fix": "Set slot content_margin_* to 6px-8px so item sprites do not touch the bezel",
                })
                break

    passed = len(failed) == 0
    next_cmd = (
        f"python game.py capture --scene {scene_posix} --json --compact"
        if passed
        else f"python game.py mockup-dissect --scene {scene_posix} --json --compact"
    )
    pipeline_connection = {
        "current_stage": "stage_3_grade",
        "next_command": next_cmd,
        "next_stage": "stage_4_capture" if passed else "stage_2_scene_first_edit",
        "passed": passed,
        "scene": scene_posix,
        "stage_2_edit": f"Edit {scene_posix} to fix failed_components, then re-run mockup-dissect and mockup-grade",
        "stage_4_capture": f"python game.py capture --scene {scene_posix} --json --compact",
    }
    return {
        "schema_version": 2,
        "cmd": "mockup-grade",
        "status": "success" if passed else "failed",
        "scene": scene_posix,
        "passed": passed,
        "probe_mode": probe_mode,
        "required_patch_margin_px": req_patch,
        "graded_control_count": len(graded_paths),
        "failed_count": len(failed),
        "failed_components": failed,
        "next_command": next_cmd,
        "pipeline_connection": pipeline_connection,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Deterministically grade UI dissection manifest")
    parser.add_argument("--manifest", default="artifacts/ui_pipeline/dissection_manifest.json", help="Path to dissection_manifest.json")
    parser.add_argument("--tolerance", type=float, default=2.0, help="Margin tolerance in pixels (default: 2.0)")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON scorecard")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path

    report = grade_dissection(manifest_path, tolerance_px=args.tolerance)
    if args.compact:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
