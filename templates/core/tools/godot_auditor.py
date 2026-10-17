#!/usr/bin/env python3
"""Godot in-game logic, physics collision matrix, Y-sort, signal wiring, and frame-budget auditor."""
import json
import re
from pathlib import Path


def parse_project_layers(project_godot: Path) -> dict:
    layers = {"2d_physics": {}, "3d_physics": {}, "2d_render": {}, "3d_render": {}}
    if not project_godot.is_file():
        return layers

    current_section = None
    for line in project_godot.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            continue
        if current_section == "layer_names/2d_physics" and "=" in line:
            k, v = line.split("=", 1)
            m = re.search(r"layer_(\d+)", k.strip())
            if m:
                layers["2d_physics"][int(m.group(1))] = v.strip().strip('"')
        elif current_section == "layer_names/3d_physics" and "=" in line:
            k, v = line.split("=", 1)
            m = re.search(r"layer_(\d+)", k.strip())
            if m:
                layers["3d_physics"][int(m.group(1))] = v.strip().strip('"')
    return layers


def audit_physics(root: Path) -> list:
    findings = []
    layers = parse_project_layers(root / "project.godot")
    valid_2d_layer_bits = set(layers["2d_physics"].keys()) if layers["2d_physics"] else set(range(1, 33))

    re_node = re.compile(r'\[node\s+name="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+parent="([^"]+)")?')
    physics_types = {"Area2D", "CharacterBody2D", "RigidBody2D", "StaticBody2D",
                     "Area3D", "CharacterBody3D", "RigidBody3D", "StaticBody3D"}

    for tscn in root.rglob("*.tscn"):
        if ".godot" in tscn.parts or ".harness" in tscn.parts:
            continue
        lines = tscn.read_text(encoding="utf-8", errors="ignore").splitlines()
        nodes = []
        current = None

        for idx, line in enumerate(lines, 1):
            line_str = line.strip()
            m = re_node.search(line_str)
            if m:
                name, ntype, parent = m.group(1), m.group(2), m.group(3)
                current = {
                    "name": name, "type": ntype, "parent": parent or ".",
                    "line": idx, "has_collider": False, "mask": None, "layer": None,
                    "y_sort": False
                }
                nodes.append(current)
                continue
            if current:
                if "collision_mask" in line_str and "=" in line_str:
                    try:
                        current["mask"] = int(line_str.split("=")[1].strip())
                    except ValueError:
                        pass
                if "collision_layer" in line_str and "=" in line_str:
                    try:
                        current["layer"] = int(line_str.split("=")[1].strip())
                    except ValueError:
                        pass
                if "y_sort_enabled = true" in line_str:
                    current["y_sort"] = True

        # Check collider child presence
        parent_paths = {n["name"] for n in nodes}
        for n in nodes:
            if n["type"] in ("CollisionShape2D", "CollisionPolygon2D", "CollisionShape3D", "CollisionPolygon3D"):
                # mark parent as having collider
                p_name = n["parent"].split("/")[-1] if n["parent"] != "." else nodes[0]["name"]
                for target in nodes:
                    if target["name"] == p_name:
                        target["has_collider"] = True

        rel_path = str(tscn.relative_to(root)).replace("\\", "/")
        for n in nodes:
            if n["type"] in physics_types:
                if not n["has_collider"]:
                    findings.append({
                        "code": "MISSING_COLLIDER",
                        "message": f"Physics node '{n['name']}' ({n['type']}) has no CollisionShape child",
                        "file": rel_path,
                        "line": n["line"],
                        "fix_hint": "Add CollisionShape2D/3D with a valid Shape resource."
                    })
                if n["mask"] is not None and layers["2d_physics"] and n["type"].endswith("2D"):
                    # Check if mask bits reference undefined layers
                    mask_val = n["mask"]
                    for bit in range(1, 33):
                        if (mask_val & (1 << (bit - 1))) and bit not in valid_2d_layer_bits:
                            findings.append({
                                "code": "DEAD_COLLISION_MASK",
                                "message": f"Node '{n['name']}' collision_mask includes bit {bit} which is not configured in project.godot",
                                "file": rel_path,
                                "line": n["line"],
                                "fix_hint": "Define layer name in project.godot or clear dead mask bit."
                            })
                            break

        # Check Y-Sort inheritance: if root or parent has y_sort_enabled, children should too
        root_node = nodes[0] if nodes else None
        if root_node and root_node.get("y_sort"):
            for child in nodes[1:]:
                if child["type"] in ("Node2D", "CharacterBody2D", "TileMapLayer") and not child["y_sort"] and child["parent"] == ".":
                    findings.append({
                        "code": "MISSING_YSORT",
                        "message": f"Parent '{root_node['name']}' has Y-Sort enabled, but child '{child['name']}' does not",
                        "file": rel_path,
                        "line": child["line"],
                        "fix_hint": "Enable y_sort_enabled = true on child node for proper depth sorting."
                    })

    return findings


def audit_exports(root: Path) -> list:
    findings = []
    # Identify hardcoded magic numbers like speed = 300, jump_force = -500, damage = 25
    re_magic = re.compile(r'^\s*(?:var|const)\s+([a-zA-Z0-9_]*(?:speed|velocity|damage|health|jump|gravity|radius|interval|timer|duration|cooldown)[a-zA-Z0-9_]*)\s*[:=]\s*(-?\d+(?:\.\d+)?)\b')
    re_export = re.compile(r'@export\b')

    for gd in root.rglob("*.gd"):
        if ".godot" in gd.parts or ".harness" in gd.parts:
            continue
        rel_path = str(gd.relative_to(root)).replace("\\", "/")
        lines = gd.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines, 1):
            if re_export.search(line):
                continue
            m = re_magic.search(line)
            if m:
                var_name, val = m.group(1), m.group(2)
                findings.append({
                    "code": "HARDCODED_MAGIC_NUMBER",
                    "message": f"Gameplay variable '{var_name} = {val}' is hardcoded instead of exposed via @export",
                    "file": rel_path,
                    "line": idx,
                    "fix_hint": f"Replace with: @export var {var_name}: float = {val}"
                })
    return findings


def audit_signals(root: Path) -> list:
    findings = []
    re_conn = re.compile(r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"')
    re_ext_script = re.compile(r'\[ext_resource\s+type="Script"\s+(?:uid="[^"]+"\s+)?path="([^"]+)"\s+id="([^"]+)"')
    re_node = re.compile(r'\[node\s+name="([^"]+)"(?:\s+type="([^"]+)")?(?:\s+parent="([^"]+)")?')

    for tscn in root.rglob("*.tscn"):
        if ".godot" in tscn.parts or ".harness" in tscn.parts:
            continue
        rel_path = str(tscn.relative_to(root)).replace("\\", "/")
        lines = tscn.read_text(encoding="utf-8", errors="ignore").splitlines()

        scripts = {}
        node_scripts = {}
        connections = []
        current_node = None

        for idx, line in enumerate(lines, 1):
            line_str = line.strip()
            m_s = re_ext_script.search(line_str)
            if m_s:
                scripts[m_s.group(2)] = m_s.group(1)
                continue
            m_n = re_node.search(line_str)
            if m_n:
                current_node = m_n.group(1)
                continue
            if current_node and "script = ExtResource" in line_str:
                m_scr = re.search(r'ExtResource\("([^"]+)"\)', line_str)
                if m_scr and m_scr.group(1) in scripts:
                    node_scripts[current_node] = scripts[m_scr.group(1)]
            m_c = re_conn.search(line_str)
            if m_c:
                connections.append({
                    "signal": m_c.group(1), "from": m_c.group(2),
                    "to": m_c.group(3), "method": m_c.group(4), "line": idx
                })

        for conn in connections:
            target_node = conn["to"]
            if target_node == ".":
                # Root node
                target_node = list(node_scripts.keys())[0] if node_scripts else None
            script_path = node_scripts.get(target_node)
            if script_path:
                clean_script = script_path.replace("res://", "")
                actual_script = root / clean_script
                if actual_script.is_file():
                    content = actual_script.read_text(encoding="utf-8", errors="ignore")
                    expected_func = f"func {conn['method']}("
                    if expected_func not in content:
                        findings.append({
                            "code": "DISCONNECTED_SIGNAL",
                            "message": f"Signal '{conn['signal']}' connected to '{conn['to']}.{conn['method']}()', but method does not exist in {script_path}",
                            "file": rel_path,
                            "line": conn["line"],
                            "fix_hint": f"Define 'func {conn['method']}():' in {clean_script}"
                        })

    return findings


def audit_perf(root: Path) -> list:
    findings = []
    # Scans _process and _physics_process for expensive calls
    in_process = False
    process_name = ""

    for gd in root.rglob("*.gd"):
        if ".godot" in gd.parts or ".harness" in gd.parts:
            continue
        rel_path = str(gd.relative_to(root)).replace("\\", "/")
        lines = gd.read_text(encoding="utf-8", errors="ignore").splitlines()

        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("func _process(") or stripped.startswith("func _physics_process("):
                in_process = True
                process_name = stripped.split("(")[0].replace("func ", "")
                continue
            elif stripped.startswith("func ") and not (stripped.startswith("func _process") or stripped.startswith("func _physics_process")):
                in_process = False

            if in_process and stripped and not stripped.startswith("#"):
                # Check for get_node, $, find_child, load
                for bad_call in ("get_node(", "find_child(", "ResourceLoader.load(", "load("):
                    if bad_call in stripped:
                        findings.append({
                            "code": "EXPENSIVE_PROCESS_CALL",
                            "message": f"Expensive call '{bad_call.rstrip('(')}' inside {process_name}() on line {idx}",
                            "file": rel_path,
                            "line": idx,
                            "fix_hint": "Cache node reference in @onready or _ready() instead of querying every frame."
                        })
                # Check for dollar sign node lookup e.g. $Sprite2D.position
                if re.search(r'\$[a-zA-Z0-9_]+', stripped) and not stripped.startswith("#"):
                    findings.append({
                        "code": "EXPENSIVE_PROCESS_CALL",
                        "message": f"Node path lookup ($Node) inside {process_name}() on line {idx}",
                        "file": rel_path,
                        "line": idx,
                        "fix_hint": "Cache with '@onready var node = $Node' rather than looking up per frame."
                    })

    return findings


def audit_scene_first(root: Path) -> list:
    findings = []
    prohibited = ("Control.new()", "Button.new()", "Label.new()", "add_theme_stylebox_override")
    for gd in root.rglob("*.gd"):
        if ".godot" in gd.parts or ".harness" in gd.parts or "test" in gd.name.lower():
            continue
        rel_path = str(gd.relative_to(root)).replace("\\", "/")
        lines = gd.read_text(encoding="utf-8", errors="ignore").splitlines()
        for idx, line in enumerate(lines, 1):
            for term in prohibited:
                if term in line:
                    findings.append({
                        "code": "UI_POLICY",
                        "message": f"Scene-First policy violation: programmatic UI construction with '{term}'",
                        "file": rel_path,
                        "line": idx,
                        "fix_hint": "Instantiate dedicated .tscn components or use Themes instead of code construction."
                    })
    return findings


def audit_project(root: Path, flags: dict = None) -> list:
    flags = flags or {}
    run_all = not any(flags.values())
    findings = []

    if run_all or flags.get("physics"):
        findings.extend(audit_physics(root))
    if run_all or flags.get("exports"):
        findings.extend(audit_exports(root))
    if run_all or flags.get("signals"):
        findings.extend(audit_signals(root))
    if run_all or flags.get("perf"):
        findings.extend(audit_perf(root))
    if run_all or flags.get("scene_first"):
        findings.extend(audit_scene_first(root))

    return findings
