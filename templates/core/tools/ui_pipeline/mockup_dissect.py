#!/usr/bin/env python3
"""Dissect mockup PNG + Godot scene bounds into artifacts/ui_pipeline/dissection_manifest.json."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bezel_profiler import DEFAULT_MEASURED_LAYERS, profile_mockup_components  # noqa: E402


def _resolve_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "project.godot").is_file() or (parent / "game.py").is_file():
            return parent
    # templates/core/tools/ui_pipeline -> parents[3] is templates or repo root
    return here.parents[3] if len(here.parents) > 3 else here.parent


REPO_ROOT = _resolve_repo_root()


def _to_posix(val: str | Path) -> str:
    return str(val).replace("\\", "/")


def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _find_godot_bin(explicit: Optional[str] = None) -> Optional[str]:
    requested = explicit or os.environ.get("GODOT4_BIN") or os.environ.get("GODOT_BIN")
    if requested:
        found = shutil.which(requested) or (requested if Path(requested).is_file() else None)
        if found:
            return found
    for name in ("godot4", "godot", "Godot"):
        found = shutil.which(name)
        if found:
            return found
    desktop = sorted((Path.home() / "Desktop").glob("Godot*.exe"))
    return str(desktop[0]) if desktop else None


def _find_probe_script(root: Path) -> Optional[Path]:
    candidates = [
        root / "core" / "tools" / "ui_pipeline" / "control_bounds_probe.gd",
        root / "tools" / "ui_pipeline" / "control_bounds_probe.gd",
        Path(__file__).resolve().parent / "control_bounds_probe.gd",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _discover_main_scene(root: Path) -> Optional[str]:
    """Auto-discover primary .tscn scene from .context/project_state.json or project.godot."""
    state_file = root / ".context" / "project_state.json"
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            main_sc = state.get("main_scene") or state.get("authored_settings", {}).get("main_scene")
            if isinstance(main_sc, str) and main_sc.strip():
                cleaned = main_sc.strip().removeprefix("res://")
                if (root / cleaned).is_file():
                    return _to_posix(cleaned)
        except (OSError, json.JSONDecodeError):
            pass

    proj_file = root / "project.godot"
    if proj_file.is_file():
        try:
            text = proj_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'(?m)^run/main_scene\s*=\s*"([^"]+)"', text)
            if m:
                raw_scene = m.group(1).strip()
                if raw_scene.startswith("res://"):
                    cleaned = raw_scene.removeprefix("res://")
                    if (root / cleaned).is_file():
                        return _to_posix(cleaned)
        except OSError:
            pass

    for candidate in ("modals/game_ui.tscn", "main.tscn", "Main.tscn", "scenes/main.tscn", "ui/hud.tscn"):
        if (root / candidate).is_file():
            return candidate

    for tscn in sorted(root.rglob("*.tscn")):
        if not any(part in (".godot", ".harness", ".agents", "tests") for part in tscn.parts):
            return _rel_posix(tscn, root)
    return None


def resolve_target_scene(root: Path, scene: Optional[str] = None) -> str:
    """Resolve explicit scene or auto-discover primary project scene when default/omitted."""
    root = Path(root).resolve()
    if scene and scene.strip():
        cleaned = _to_posix(scene.strip().removeprefix("res://"))
        if (root / cleaned).is_file():
            return cleaned
        # If the caller used the legacy default "modals/game_ui.tscn" and it doesn't exist, try auto-discovery
        if cleaned == "modals/game_ui.tscn":
            discovered = _discover_main_scene(root)
            if discovered:
                return discovered
        return cleaned
    discovered = _discover_main_scene(root)
    return discovered or "modals/game_ui.tscn"


def _read_art_style_direction(root: Path) -> str:
    state_file = root / ".context" / "project_state.json"
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            val = state.get("art_style_direction") or state.get("art_style") or ""
            if isinstance(val, str) and val.strip() and val.strip().lower() not in ("unset", "none", "tbd", "null"):
                return val.strip()
        except (OSError, json.JSONDecodeError):
            pass

    style_guide = root / "docs" / "art" / "style_guide.md"
    if style_guide.is_file():
        try:
            text = style_guide.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return "docs/art/style_guide.md"
        except OSError:
            pass
    return ""


def check_prerequisites(
    root: Path,
    scene: Optional[str] = None,
    mockup: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate Stage 0 UI pipeline prerequisites before dissecting or authoring UI."""
    root = Path(root).resolve()
    resolved_scene = resolve_target_scene(root, scene)
    scene_file = root / resolved_scene.removeprefix("res://")
    scene_exists = scene_file.is_file()

    has_pillow = importlib.util.find_spec("PIL") is not None
    mockup_rel = _to_posix(mockup.strip()) if (mockup and mockup.strip()) else ""
    mockup_used = bool(mockup_rel)
    mockup_exists = (root / mockup_rel).is_file() if mockup_used else False

    findings: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []

    if not scene_exists:
        findings.append({
            "code": "PREREQ_SCENE_MISSING",
            "file": resolved_scene,
            "fix_hint": f"Create or pass an existing target .tscn scene via --scene (missing: {resolved_scene})",
            "message": f"Target scene does not exist: {resolved_scene}",
            "severity": "error",
        })

    if mockup_used and not has_pillow:
        findings.append({
            "code": "PREREQ_PILLOW_MISSING",
            "file": mockup_rel,
            "fix_hint": "Install Pillow (pip install Pillow) so bezel_profiler can measure mockup pixel layers",
            "message": "Pillow (PIL) is required when a mockup image is provided",
            "severity": "error",
        })

    # Check .gdignore shielding in docs/ or assets/ui/staging/ when present
    gdignore_missing_dirs: List[str] = []
    for candidate_dir in ("docs", "assets/ui/staging"):
        dpath = root / candidate_dir
        if dpath.is_dir() and not (dpath / ".gdignore").is_file():
            gdignore_missing_dirs.append(candidate_dir)
    if gdignore_missing_dirs:
        findings.append({
            "code": "PREREQ_GDIGNORE_MISSING",
            "file": ", ".join(f"{d}/.gdignore" for d in gdignore_missing_dirs),
            "fix_hint": "Create an empty .gdignore file in docs/ and assets/ui/staging/ so Godot does not import reference mockups",
            "message": f"Missing .gdignore in staging/documentation directories: {', '.join(gdignore_missing_dirs)}",
            "severity": "warning",
        })

    art_style = _read_art_style_direction(root)
    art_style_configured = bool(art_style)
    if not art_style_configured:
        advisory = {
            "code": "ART_STYLE_DIRECTION_UNSET",
            "file": ".context/project_state.json",
            "fix_hint": "Explicitly ask the user to decide and define their art & UI style direction before creating mockups or UI assets",
            "message": "Explicitly ask the user to decide and define their art & UI style direction before creating mockups or UI assets",
            "severity": "advisory",
        }
        advisories.append(advisory)
        findings.append(advisory)

    blocking_errors = [f for f in findings if f.get("severity") == "error"]
    ok = len(blocking_errors) == 0

    return {
        "advisories": advisories,
        "art_style_configured": art_style_configured,
        "art_style_direction": art_style,
        "ask_user_art_style": not art_style_configured,
        "cmd": "mockup-dissect",
        "findings": findings,
        "gdignore_missing_dirs": gdignore_missing_dirs,
        "mockup": mockup_rel,
        "mockup_exists": mockup_exists,
        "ok": ok,
        "passed": ok,
        "pillow_available": has_pillow,
        "scene": resolved_scene,
        "scene_exists": scene_exists,
        "schema_version": 2,
        "status": "success" if ok else "failed",
    }


def _parse_tscn_fallback(scene_path: Path) -> List[Dict[str, Any]]:
    """Fallback static parser extracting StyleBoxTexture/Flat & node names from .tscn."""
    if not scene_path.is_file():
        return []
    text = scene_path.read_text(encoding="utf-8", errors="ignore")
    ext_resources: Dict[str, str] = {}
    for line in text.splitlines():
        m_ext = re.match(r'^\[ext_resource\s+.*?\bid="([^"]+)"', line.strip())
        if m_ext:
            ext_id = m_ext.group(1)
            m_path = re.search(r'\bpath="([^"]+)"', line)
            if m_path:
                ext_resources[ext_id] = m_path.group(1)

    sub_styles: Dict[str, Dict[str, Any]] = {}
    cur_id: Optional[str] = None
    cur_data: Dict[str, Any] = {}

    def flush_sub() -> None:
        if cur_id and cur_data:
            sub_styles[cur_id] = cur_data

    for line in text.splitlines():
        m_sub = re.match(r'^\[sub_resource type="(StyleBoxTexture|StyleBoxFlat)" id="([^"]+)"\]', line.strip())
        if m_sub:
            flush_sub()
            cur_id = m_sub.group(2)
            cur_data = {
                "type": m_sub.group(1),
                "content_margin_left": 0.0,
                "content_margin_top": 0.0,
                "content_margin_right": 0.0,
                "content_margin_bottom": 0.0,
            }
            if m_sub.group(1) == "StyleBoxTexture":
                cur_data.update({
                    "patch_margin_left": 0.0,
                    "patch_margin_top": 0.0,
                    "patch_margin_right": 0.0,
                    "patch_margin_bottom": 0.0,
                    "texture": "",
                })
            else:
                cur_data.update({
                    "border_width_left": 0.0,
                    "border_width_top": 0.0,
                    "border_width_right": 0.0,
                    "border_width_bottom": 0.0,
                    "corner_radius_top_left": 0.0,
                })
            continue
        if line.startswith("["):
            flush_sub()
            cur_id = None
            cur_data = {}
            continue
        if cur_id and "=" in line:
            k, v = [p.strip() for p in line.split("=", 1)]
            if k.startswith("texture_margin_") or k.startswith("patch_margin_"):
                side = k.replace("texture_margin_", "patch_margin_")
                try:
                    cur_data[side] = float(v)
                except ValueError:
                    pass
            elif k == "texture":
                m_ext_ref = re.search(r'ExtResource\(\s*"([^"]+)"\s*\)', v)
                if m_ext_ref:
                    cur_data["texture"] = ext_resources.get(m_ext_ref.group(1), "")
            elif k.startswith(("content_margin_", "border_width_", "corner_radius_")):
                try:
                    cur_data[k] = float(v)
                except ValueError:
                    pass

    flush_sub()

    controls: List[Dict[str, Any]] = []
    cur_node: Optional[Dict[str, Any]] = None
    cur_offsets: Dict[str, float] = {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}

    def flush_node() -> None:
        nonlocal cur_node
        if cur_node is not None:
            left = cur_offsets["left"]
            top = cur_offsets["top"]
            right = cur_offsets["right"]
            bottom = cur_offsets["bottom"]
            if right > left or bottom > top or left != 0.0 or top != 0.0:
                cur_node["rect"] = {
                    "x": left,
                    "y": top,
                    "w": max(0.0, right - left),
                    "h": max(0.0, bottom - top),
                }
            controls.append(cur_node)
            cur_node = None

    for line in text.splitlines():
        m_node = re.match(r'^\[node name="([^"]+)" type="([^"]+)"(?:\s+parent="([^"]*)")?', line.strip())
        if m_node:
            flush_node()
            name, ntype, parent = m_node.group(1), m_node.group(2), m_node.group(3) or ""
            path = f"{parent}/{name}" if parent and parent != "." else name
            cur_offsets = {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0}
            cur_node = {
                "name": name,
                "path": path,
                "class": ntype,
                "visible": True,
                "rect": {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                "custom_minimum_size": {"x": 0.0, "y": 0.0},
                "styles": {},
            }
            continue
        if line.startswith("["):
            flush_node()
            continue
        if cur_node and "=" in line:
            k, v = [p.strip() for p in line.split("=", 1)]
            if k == "visible":
                cur_node["visible"] = v.lower() != "false"
            elif k == "custom_minimum_size":
                m_vec = re.search(r"Vector2i?\(\s*([0-9.-]+)\s*,\s*([0-9.-]+)\s*\)", v)
                if m_vec:
                    cur_node["custom_minimum_size"] = {
                        "x": float(m_vec.group(1)),
                        "y": float(m_vec.group(2)),
                    }
            elif k.startswith("theme_override_styles/"):
                sname = k.split("/", 1)[1]
                m_sr = re.search(r'SubResource\(\s*"([^"]+)"\s*\)', v)
                if m_sr and m_sr.group(1) in sub_styles:
                    cur_node["styles"][sname] = dict(sub_styles[m_sr.group(1)])
            elif k in ("offset_left", "offset_top", "offset_right", "offset_bottom"):
                try:
                    side = k.replace("offset_", "")
                    cur_offsets[side] = float(v)
                except ValueError:
                    pass
    flush_node()
    return controls


def run_bounds_probe(
    root: Path,
    scene_rel: str,
    godot_bin: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Run headless control_bounds_probe.gd, falling back to .tscn static parse if needed."""
    binary = _find_godot_bin(godot_bin)
    probe_gd = _find_probe_script(root)
    res_scene = scene_rel if scene_rel.startswith("res://") else "res://" + Path(scene_rel).as_posix().lstrip("/")

    if binary and probe_gd and probe_gd.is_file():
        env = os.environ.copy()
        env["GAME_PROBE_SCENE"] = res_scene
        try:
            completed = subprocess.run(
                [binary, "--headless", "--path", str(root), "--script", str(probe_gd)],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            for line in (completed.stdout + "\n" + completed.stderr).splitlines():
                if line.startswith("HARNESS_JSON="):
                    payload = json.loads(line[len("HARNESS_JSON="):])
                    if payload.get("ok") and payload.get("controls"):
                        return {
                            "probe_mode": "godot_runtime",
                            "controls": payload["controls"],
                            "viewport": payload.get("viewport", [1280, 720]),
                        }
        except Exception:
            pass

    scene_file = root / scene_rel.removeprefix("res://")
    return {
        "probe_mode": "tscn_fallback",
        "controls": _parse_tscn_fallback(scene_file),
        "viewport": [1280, 720],
    }


def _find_control(controls: List[Dict[str, Any]], names: List[str]) -> Optional[Dict[str, Any]]:
    lower_names = [n.lower() for n in names]
    for target in lower_names:
        for ctrl in controls:
            if ctrl.get("name", "").lower() == target:
                return ctrl
    for target in lower_names:
        for ctrl in controls:
            if target in ctrl.get("path", "").lower():
                return ctrl
    return None


def _extract_styled_controls(controls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract all Control nodes that have at least one StyleBoxTexture or StyleBoxFlat override."""
    styled: List[Dict[str, Any]] = []
    for ctrl in controls:
        styles = ctrl.get("styles", {})
        if not isinstance(styles, dict) or not styles:
            continue
        has_graded_style = any(
            isinstance(sb, dict) and sb.get("type") in ("StyleBoxTexture", "StyleBoxFlat")
            for sb in styles.values()
        )
        if has_graded_style:
            styled.append(ctrl)
    return styled


def build_pipeline_connection(scene_posix: str, dissection_rel_posix: str) -> Dict[str, Any]:
    """Build explicit 5-stage pipeline connection metadata linking Stage 1 -> Stage 2 -> Stage 3 -> Stage 4."""
    return {
        "current_stage": "stage_1_dissect",
        "next_command": f"python game.py mockup-grade --manifest {dissection_rel_posix} --json --compact",
        "next_stage": "stage_2_scene_first_edit",
        "stage_0_prereqs": f"python game.py mockup-dissect --scene {scene_posix} --check-prereqs --json --compact",
        "stage_1_dissect": f"python game.py mockup-dissect --scene {scene_posix} --json --compact",
        "stage_2_edit": f"Edit {scene_posix} StyleBoxTexture/StyleBoxFlat margins in .tscn (Scene-First; no Control.new()), then run: python game.py validate --uid --json --compact",
        "stage_3_grade": f"python game.py mockup-grade --manifest {dissection_rel_posix} --json --compact",
        "stage_4_capture": f"python game.py capture --scene {scene_posix} --json --compact",
    }


def dissect_ui(
    root: Path,
    scene: Optional[str] = "modals/game_ui.tscn",
    mockup: Optional[str] = "docs/art/farm_hud_polish_v2/mockup_hd_v03_flat.png",
    out_dir: str = "artifacts/ui_pipeline",
    godot: Optional[str] = None,
    timeout: float = 30.0,
    check_prereqs: bool = False,
) -> Dict[str, Any]:
    """Produce dissection_manifest.json and manifest.json with sort_keys=True and POSIX paths."""
    root = Path(root).resolve()
    resolved_scene = resolve_target_scene(root, scene)
    prereqs = check_prerequisites(root, scene=resolved_scene, mockup=mockup)
    if check_prereqs:
        return prereqs

    out_path = (root / out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    crops_dir = out_path / "crops"

    mockup_file = (root / mockup) if (mockup and mockup.strip()) else None
    mockup_info = profile_mockup_components(mockup_file, crops_dir) if mockup_file else {
        "mockup_present": False,
        "mockup_path": "",
        "measured_layers_px": dict(DEFAULT_MEASURED_LAYERS),
        "slices": {},
    }
    if mockup_file and mockup_info.get("mockup_path"):
        mockup_info["mockup_path"] = _rel_posix(mockup_file, root)

    probe_info = run_bounds_probe(root, resolved_scene, godot_bin=godot, timeout=timeout)
    controls = probe_info["controls"]
    styled_controls = _extract_styled_controls(controls)

    key_map = {
        "HD01_TopLeftPanel": _find_control(controls, ["TopLeftPanel"]),
        "HD02_ProfileCard": _find_control(controls, ["ProfileCard"]),
        "HD03_MiniCalendarWidget": _find_control(controls, ["MiniCalendarWidget", "CalendarWidget"]),
        "HD04_QuestPanel": _find_control(controls, ["CampfireCompass", "QuestPanel", "QuestStrip"]),
        "HD05_HotbarWrapper": _find_control(controls, ["HotbarWrapper", "HotbarPanel"]),
        "HD06_LevelLabel": _find_control(controls, ["LevelLabel"]),
        "HD07_LevelProgressBar": _find_control(controls, ["LevelProgressBar"]),
        "HD08_EnergyLabel": _find_control(controls, ["EnergyLabel"]),
        "HD09_EnergyProgressBar": _find_control(controls, ["EnergyProgressBar", "EnergyBar"]),
    }

    dissection_file = out_path / "dissection_manifest.json"
    dissection_rel = _rel_posix(dissection_file, root)
    scene_posix = _to_posix(resolved_scene)
    pipeline_conn = build_pipeline_connection(scene_posix, dissection_rel)

    manifest = {
        "schema_version": 2,
        "scene": scene_posix,
        "mockup": _to_posix(mockup_info["mockup_path"]),
        "mockup_present": mockup_info["mockup_present"],
        "probe_mode": probe_info["probe_mode"],
        "viewport": probe_info["viewport"],
        "measured_layers_px": mockup_info["measured_layers_px"],
        "slices": mockup_info["slices"],
        "styled_control_count": len(styled_controls),
        "styled_controls": styled_controls,
        "key_components": {k: v for k, v in key_map.items() if v is not None},
        "control_count": len(controls),
        "controls": controls,
        "prerequisites": {
            "art_style_configured": prereqs["art_style_configured"],
            "art_style_direction": prereqs["art_style_direction"],
            "ask_user_art_style": prereqs["ask_user_art_style"],
            "findings": prereqs["findings"],
            "ok": prereqs["ok"],
        },
        "pipeline_connection": pipeline_conn,
    }

    dissection_file.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    handoff_file = out_path / "manifest.json"
    handoff_payload = {
        "schema_version": 2,
        "scene": manifest["scene"],
        "dissection_manifest": dissection_file.as_posix(),
        "measured_layers_px": manifest["measured_layers_px"],
        "probe_mode": manifest["probe_mode"],
        "styled_control_count": len(styled_controls),
        "pipeline_connection": pipeline_conn,
    }
    handoff_file.write_text(
        json.dumps(handoff_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "dissection_manifest": dissection_file.as_posix(),
        "handoff_manifest": handoff_file.as_posix(),
        "manifest": manifest,
        "pipeline_connection": pipeline_conn,
        "prerequisites": prereqs,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Dissect UI scene bounds and mockup pixel layers")
    parser.add_argument("--scene", default=None, help="Target .tscn scene (auto-discovered if omitted)")
    parser.add_argument("--mockup", default="docs/art/farm_hud_polish_v2/mockup_hd_v03_flat.png", help="Reference mockup PNG")
    parser.add_argument("--out-dir", default="artifacts/ui_pipeline", help="Artifact output directory")
    parser.add_argument("--godot", default=None, help="Explicit Godot binary")
    parser.add_argument("--check-prereqs", action="store_true", help="Check Stage 0 UI pipeline prerequisites and art style gate")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON summary")
    args = parser.parse_args()

    if args.check_prereqs:
        prereq_res = check_prerequisites(REPO_ROOT, scene=args.scene, mockup=args.mockup)
        if args.compact:
            print(json.dumps(prereq_res, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(prereq_res, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if prereq_res["ok"] else 1

    res = dissect_ui(REPO_ROOT, scene=args.scene, mockup=args.mockup, out_dir=args.out_dir, godot=args.godot)
    if args.compact:
        m = res["manifest"]
        print(json.dumps({
            "schema_version": 2,
            "cmd": "mockup-dissect",
            "status": "success",
            "scene": m["scene"],
            "probe_mode": m["probe_mode"],
            "control_count": m["control_count"],
            "styled_control_count": m["styled_control_count"],
            "measured_layers_px": m["measured_layers_px"],
            "dissection_manifest": res["dissection_manifest"],
            "pipeline_connection": m["pipeline_connection"],
        }, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(res["manifest"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
