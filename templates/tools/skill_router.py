#!/usr/bin/env python3
"""
tools/skill_router.py - Deterministic 3-Layer Prompt-to-Skill & Graphify Router for Godot Dynamic Harness (GDH).

Implements the zero-bypass router protocol:
- Layer 1: Core Always-On Skills (project-context, i-have-adhd, agent-coordination, graphify)
- Layer 2: Deterministic Conditional Mode Rules (caveman_full vs prose; cozy-hd-ui vs harvest-moon-sprite Dual-Fidelity Art Split)
- Layer 3: Complete 46-Skill Keyword & Synonym Dictionary + Dynamic Frontmatter Discovery
- Active Graphify Query & Graph Neighbor Executor with fallback
- Change Classification (tier & verification checks)
- Audit Trail Logging (.agent-state/logs/router_audit.jsonl)
- Receipt Markdown Formatter

Standard library + optional graphify integration.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Repository root detection
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
if os.environ.get("GDH_ROOT"):
    _REPO_ROOT = Path(os.environ["GDH_ROOT"]).resolve()
elif os.environ.get("AGENT_LOCK_ROOT"):
    _REPO_ROOT = Path(os.environ["AGENT_LOCK_ROOT"]).resolve()

REPO_ROOT = _REPO_ROOT
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"

# Layer 1: Default core skills (project-context dynamically resolved if present)
DEFAULT_CORE_SKILLS: List[str] = [
    "moonveil-context",
    "i-have-adhd",
    "agent-coordination",
    "graphify",
]
CORE_SKILLS: List[str] = list(DEFAULT_CORE_SKILLS)

# Layer 2 categories
CODING_CATEGORIES = {"coding", "bugfix", "tuning", "qa", "refactor"}
PROSE_CATEGORIES = {"planning", "docs_or_lore", "architecture_query"}

# Complete 46-Skill Dictionary covering standard Godot harness & game skills
SKILL_DICTIONARY: Dict[str, List[str]] = {
    "2d-essentials": [
        "2d-essentials", "tilemaps", "tilemap", "tilemaplayer", "terrain", "autotiling",
        "parallax", "parallax scrolling",
        "2d light", "2d lights", "2d shadow", "2d shadows", "canvaslayer", "canvas layer",
        "particles 2d", "particles2d", "gpuparticles2d", "cpuparticles2d",
        "custom drawing", "2d mesh", "2d meshes", "canvasitem", "draw_rect", "draw_circle"
    ],
    "agent-coordination": [
        "agent-coordination", "agent coordination", "agent lock", "agent_lock", "lease",
        "leases", "file locking", "concurrency safety", "lease handoff", "unified write-off",
        "journaling", "journal.jsonl", "leases.json", "ownership matrix", "lock collision"
    ],
    "cavecrew": [
        "cavecrew", "multi-agent handoff", "bounded agent", "worker brief", "lead and worker",
        "delegation", "subagent", "subagents", "squad matrix", "investigator", "builder",
        "reviewer", "lead integrator"
    ],
    "caveman": [
        "caveman", "caveman mode", "ultra-compressed", "less tokens", "talk like caveman",
        "terse", "concise output", "compression mode"
    ],
    "caveman-compress": [
        "caveman-compress", "/caveman-compress", "compress memory", "compress claude.md",
        "compress todo", "trim tokens", "token sink"
    ],
    "cozy-hd-ui": [
        "cozy-hd-ui", "game ui", "hud", "hud panel", "hud panels", "menu", "menus", "modal",
        "modals", "dialog", "dialogs", "dialogue box", "hotbar", "button", "buttons",
        "stat bar", "stat bars", "ui icon", "ui icons", "mockup v03", "mockup_hd_v03_flat.png",
        "flat 2d cozy hd vector ui", "styleboxtexture", "ivory", "timber border", "9-patch",
        "vector ui", "#f3e5c9", "#4c2b13", "#e2cca5", "#b77739", "#e8ae24", "#48a83c"
    ],
    "godot-2d-animation": [
        "godot-2d-animation", "animatedsprite2d", "spriteframes", "animation_finished",
        "animation_looped", "frame_changed", "frame_progress", "set_frame_and_progress",
        "cutout animation", "skeletal 2d", "bone2d", "procedural animation",
        "animation state machine", "squash and stretch", "advance(0)"
    ],
    "godot-2d-physics": [
        "godot-2d-physics", "2d physics", "collisionshape2d", "collisionpolygon2d",
        "collision_layer", "collision_mask", "set_collision_layer_value",
        "set_collision_mask_value", "area2d", "body_entered", "body_exited", "raycast2d",
        "force_raycast_update", "physicspointqueryparameters2d", "physicsshapequeryparameters2d",
        "direct_space_state", "move_and_collide"
    ],
    "godot-agent-vision": [
        "godot-agent-vision", "agent vision", "screenshot", "webp", "visual qa",
        "taste receptors", "taste receptor atlas", "typography review", "ui review",
        "asset sheet", "editor viewport", "anti-slop"
    ],
    "godot-animation-player": [
        "godot-animation-player", "animationplayer", "animation", "track_insert_key",
        "root_motion", "reset track", "reset_track", "call_mode", "animation_set_next",
        "blend_times", "track types"
    ],
    "godot-audio-systems": [
        "godot-audio-systems", "audiostreamplayer", "audiostreamplayer2d",
        "audiostreamplayer3d", "audiobus", "audioserver", "audioeffect", "music_crossfade",
        "music crossfade", "audio_pool", "audio pool", "positional_audio", "positional audio",
        "reverb", "bus_volume", "sound effect", "sfx", "bgm", "audio bus"
    ],
    "godot-autoload-architecture": [
        "godot-autoload-architecture", "autoload", "autoloads", "singleton", "singletons",
        "gamemanager", "game manager", "game_manager", "eventbus", "event bus", "event_bus",
        "savesystem", "save system", "save_system", "scenetransitioner", "global_state",
        "global state", "autoload_order", "autoload order", "signal_bus", "dependency_injection"
    ],
    "godot-camera-systems": [
        "godot-camera-systems", "camera2d", "camera3d", "springarm3d", "position_smoothing",
        "camera_shake", "camera shake", "trauma_system", "trauma system", "look_ahead",
        "drag_margin", "camera_limits", "camera limits", "camera_transition", "camera transition"
    ],
    "godot-characterbody-2d": [
        "godot-characterbody-2d", "characterbody2d", "move_and_slide", "is_on_floor",
        "coyote_time", "coyote time", "jump_buffer", "jump buffering", "variable jump",
        "velocity", "get_slide_collision", "one_way_platforms", "one-way platforms",
        "top-down movement", "8-way movement"
    ],
    "godot-composition": [
        "godot-composition", "entity-component", "entity component", "ecs", "gameplay",
        "actors", "enemies", "weapons", "hitboxes", "hitbox", "hurtbox", "game loop",
        "has-a", "composition pattern"
    ],
    "godot-dialogue-system": [
        "godot-dialogue-system", "dialogueline", "dialoguechoice", "dialoguegraph",
        "dialogue_manager", "typewriter_effect", "typewriter", "branching_dialogue",
        "branching dialogue", "dialogue_flags", "dialogue flags", "dialogue", "dialog",
        "npc conversation", "voice acting"
    ],
    "godot-economy-system": [
        "godot-economy-system", "economymanager", "economy", "currency", "shop_item",
        "shop item", "loot_table", "loot table", "dynamic_pricing", "buy_sell_spread",
        "buy sell", "currency_sink", "currency sink", "inflation", "item_rarity",
        "gold", "wallet", "merchant", "pricing"
    ],
    "godot-game-loop-collection": [
        "godot-game-loop-collection", "collectible_id", "collectible", "collectibles",
        "scavenger_hunt", "scavenger hunt", "collection_manager", "collection manager",
        "collection_compass", "collection compass", "completion_archive", "completion archive",
        "hidden_item_spawner", "hidden item", "find_all", "collectible_item"
    ],
    "godot-game-loop-harvest": [
        "godot-game-loop-harvest", "apply_hit", "harvestresourcedata", "harvesttooldata",
        "respawn_manager", "tool tier", "harvestable_node", "harvestable", "fastnoiselite veins",
        "mining", "logging", "foraging", "tree chopping", "stone mining", "rock breaking", "harvest loop"
    ],
    "godot-gdscript-mastery": [
        "godot-gdscript-mastery", "gdscript", "static_typing", "static typing",
        "signal_architecture", "unique_nodes", "%uniquename", "@onready", "class_name",
        "signal_up_call_down", "signal-up", "call-down", "callable.bind", "callable",
        "typed_collections", "typed collections", "await_sequence", "await sequence"
    ],
    "godot-genre-survival": [
        "godot-genre-survival", "survival", "needs system", "crafting", "hunger", "thirst",
        "stamina", "fatigue", "resource gathering", "base building", "survival stats",
        "vitals", "exposure"
    ],
    "godot-input-handling": [
        "godot-input-handling", "inputmap", "inputevent", "gamepad", "controller",
        "rebinding", "deadzone", "input buffer", "input buffering", "touch input",
        "keybind", "joystick"
    ],
    "godot-inventory-system": [
        "godot-inventory-system", "inventory", "slot", "stack", "equipment", "max_stack",
        "drag-drop", "drag and drop", "bag", "chest", "chest inventory", "grid inventory",
        "inventory_manager", "inventory slot"
    ],
    "godot-multiplayer-networking": [
        "godot-multiplayer-networking", "multiplayer", "rpc", "enetmultiplayerpeer",
        "multiplayersynchronizer", "multiplayerspawner", "authority", "client prediction",
        "rollback", "interest management", "desync", "rubber-banding", "enet", "playit",
        "udp networking", "network_manager"
    ],
    "godot-project-foundations": [
        "godot-project-foundations", "project organization", "naming conventions",
        "snake_case", "pascalcase", "feature-based", ".gitignore", ".gdignore",
        "project foundations", "folder structure"
    ],
    "godot-quest-system": [
        "godot-quest-system", "quest", "quests", "objectives", "quest resource",
        "questobjective", "quest chain", "branching chain", "quest rewards",
        "quest_manager", "quest tracking"
    ],
    "godot-resource-data-patterns": [
        "godot-resource-data-patterns", "resource", "refcounted", "itemdata",
        "characterstats", "item database", "custom resource", "serialization",
        "@export resource", "typed arrays", "data-oriented"
    ],
    "godot-save-load-systems": [
        "godot-save-load-systems", "save", "load", "save system", "savesystem", "user://",
        "fileaccess", "persist group", "save profile", "slot save", "save migration",
        "save/load", "persistence"
    ],
    "godot-scene-management": [
        "godot-scene-management", "scene loading", "scene transition", "async loading",
        "resourceloader", "change_scene", "scenetransition", "packedscene", "scene fade",
        "loading screen"
    ],
    "godot-server-architecture": [
        "godot-server-architecture", "dedicated server", "headless server", "dtls",
        "safe_packet_decoder", "multiplayer host", "websocketmultiplayerpeer",
        "server authority", "server telemetry", "multiplayer", "rpc", "rollback",
        "desync", "client prediction", "authority"
    ],
    "godot-signal-architecture": [
        "godot-signal-architecture", "signal", "signals", "signal up call down",
        "signal-up/call-down", "connect_one_shot", "connect_reference_counted",
        "event bus", "event_bus", "signal decoupling", "typed signals"
    ],
    "godot-state-machine-advanced": [
        "godot-state-machine-advanced", "state machine", "hsm", "hierarchical state machine",
        "pushdown automata", "state stack", "fsm", "ai behavior", "sub-state"
    ],
    "godot-testing-patterns": [
        "godot-testing-patterns", "gdunit4", "gdunittsuite", "headless ci", "snapshot test",
        "mock network", "scene integration test", "tdd", "unit test", "test suite", "testing"
    ],
    "godot-tilemap-mastery": [
        "godot-tilemap-mastery", "tilemaplayer", "tileset", "terrain autotiling",
        "autotiling", "physics layer", "custom data layer", "destructible tiles",
        "tilemap", "world_grid", "tile grid"
    ],
    "godot-tweening": [
        "godot-tweening", "tween", "tweening", "create_tween", "tween_property",
        "tween_callback", "easing", "ease_in_out", "trans_cubic", "property transition", "juice"
    ],
    "godot-ui-containers": [
        "godot-ui-containers", "container", "hboxcontainer", "vboxcontainer", "gridcontainer",
        "margincontainer", "scrollcontainer", "hflowcontainer", "subviewportcontainer",
        "virtual_list", "stretch_shrink", "size_flags", "expand_fill", "anchors", "responsive ui"
    ],
    "godot-ui-theming": [
        "godot-ui-theming", "theme", "stylebox", "styleboxflat", "add_theme_override",
        "custom font", "theme inheritance", "dark mode", "font variation", "theme resource"
    ],
    "graphify": [
        "graphify", "knowledge graph", "codebase graph", "graph query", "god nodes",
        "community detection", "graph report", "call graph", "graph.json"
    ],
    "harvest-moon-sprite": [
        "harvest-moon-sprite", "harvest moon", "world sprite", "world sprites",
        "16x16", "32x32", "fomt", "mfomt", "bgr555", "ground contact", "crop sprite",
        "selective outline", "water edge curve", "mountain elevation", "pixel art sprite"
    ],
    "i-have-adhd": [
        "i-have-adhd", "adhd", "next action", "numbered steps", "action-first",
        "suppress tangents", "restate state"
    ],
    "image-bg-removal": [
        "image-bg-removal", "background removal", "transparent background", "transparent png",
        "chroma key", "remove-background", "green screen", "inspyrenet", "alpha cutout"
    ],
    "moonveil-context": [
        "moonveil-context", "moonveil", "moonveil sanctuary", "farming rpg",
        "project context", "autoloads", "source folders", "game architecture"
    ],
    "pixel-art-gen": [
        "pixel-art-gen", "render_pixel_art.py", "render_pixel_art", "scripted pixel art",
        "procedural pixel art", "pixel generation"
    ],
    "ponytail": [
        "ponytail", "lazy senior dev", "smallest change", "simplest solution", "yagni",
        "least new code", "least code"
    ],
    "prompt-master": [
        "prompt-master", "prompt engineering", "optimize prompt", "system prompt",
        "agent prompt", "llm prompt"
    ],
    "token-budget": [
        "token-budget", "token budget", "context boundary", "3-tier context",
        "token limit", "token optimization", "context compression"
    ]
}

# Backward compatibility alias
SKILL_KEYWORD_MAP = SKILL_DICTIONARY

COMMON_STOPWORDS = {
    "the", "a", "an", "is", "in", "to", "for", "and", "or", "of", "with", "at",
    "by", "from", "up", "about", "into", "over", "after", "it", "this", "that",
    "these", "those", "all", "each", "every", "some", "any", "no", "not", "only",
    "game", "godot", "when", "using", "used", "make", "building", "expert", "patterns",
    "systems", "system", "tools", "data", "code", "files", "file", "which", "their",
    "other", "more", "also", "into", "such", "than", "will", "would", "could", "should"
}


def discover_disk_skills(skills_dir: Path) -> Dict[str, List[str]]:
    """
    Scans .agents/skills/*/SKILL.md frontmatter for all skills present on disk.
    Extracts name, description keywords, and synonyms.
    """
    discovered: Dict[str, List[str]] = {}
    if not skills_dir.is_dir():
        return discovered
    for d in skills_dir.iterdir():
        if d.is_dir():
            skill_md = d / "SKILL.md"
            if skill_md.is_file():
                name = d.name
                keywords = [name, name.replace("-", " "), name.replace("_", " ")]
                try:
                    content = skill_md.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL | re.MULTILINE)
                    if m:
                        frontmatter = m.group(1)
                        name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
                        if name_match:
                            val = name_match.group(1).strip().strip('"\'')
                            if val and val not in keywords:
                                keywords.append(val)
                                keywords.append(val.replace("-", " "))
                        desc_match = re.search(
                            r"^description:\s*(?:[>|]-?\s*)?\n?((?:(?:\s{2,}|\t).*\n?)+|.+)",
                            frontmatter,
                            re.MULTILINE
                        )
                        desc_text = desc_match.group(1) if desc_match else ""
                        if desc_text:
                            words = [
                                w.lower() for w in re.findall(r"\b[a-zA-Z_\-]{4,}\b", desc_text)
                                if w.lower() not in COMMON_STOPWORDS
                            ]
                            for w in words[:15]:
                                if w not in keywords:
                                    keywords.append(w)
                except Exception:
                    pass
                discovered[name] = keywords
    return discovered


def auto_dissect_prompt(raw_prompt: str) -> Dict[str, Any]:
    """Auto-dissects a raw prompt string into a structured prompt dictionary."""
    lower = raw_prompt.lower()

    # 1. Target files extraction
    file_matches = re.findall(r'[\w./\\-]+\.(?:tscn|gd|tres|md|json|gdshader|txt|png|py)', raw_prompt)
    target_files = []
    for fm in file_matches:
        if fm not in target_files:
            target_files.append(fm)

    # 2. Task category classification
    if any(w in lower for w in ["bug", "fix", "error", "crash", "issue", "fault", "broken", "desync"]):
        task_category = "bugfix"
    elif any(w in lower for w in ["refactor", "cleanup", "clean up", "restructure", "reorganize", "deprecate"]):
        task_category = "refactor"
    elif any(w in lower for w in ["test", "tests", "qa", "verify", "audit", "syntax", "validate", "baseline", "capture"]):
        task_category = "qa"
    elif any(w in lower for w in ["tune", "balance", "speed", "perf", "performance", "optimize", "fps"]):
        task_category = "tuning"
    elif any(w in lower for w in ["plan", "planning", "roadmap", "architecture", "design", "rfc", "proposal"]):
        task_category = "planning"
    elif any(w in lower for w in ["doc", "docs", "documentation", "readme", "lore", "story", "dialogue", "dialog", "walkthrough", "guide"]):
        task_category = "docs_or_lore"
    elif any(w in lower for w in ["how does", "what calls", "explain", "trace", "where is", "why does", "understand"]):
        task_category = "architecture_query"
    else:
        task_category = "coding"

    # 3. Dual-Fidelity Art Domain classification
    ui_indicators = [
        "ui", "hud", "modal", "menu", "theme", "button", "panel", "font", "slot",
        "hotbar", "inventory_slot", "dialogue_box", "toast", "crafting_ui", "stylebox",
        "margincontainer", "vboxcontainer", "hboxcontainer", "gridcontainer", "vector ui",
        "mockup", "profile_card", "gold_display", "time_display"
    ]
    world_sprite_indicators = [
        "world_sprite", "sprite", "crop", "16x16", "32x32", "tile", "tileset", "boulder",
        "tree", "animal", "pixel-art", "pixel art", "ground item", "fomt", "mfomt",
        "forageable", "pickup_item", "ore_deposit"
    ]

    has_ui = any(re.search(r'\b' + re.escape(w) + r'\b', lower) for w in ui_indicators) or any(
        f.endswith(".tscn") and any(u in f.lower() for u in ["ui", "hud", "menu", "modal", "slot", "button"])
        for f in target_files
    )
    has_sprite = any(re.search(r'\b' + re.escape(w) + r'\b', lower) for w in world_sprite_indicators)

    if has_ui and not has_sprite:
        art_domain = "ui"
    elif has_sprite and not has_ui:
        art_domain = "world_sprite"
    elif has_ui and has_sprite:
        art_domain = "ui" if ("hud" in lower or "menu" in lower or "button" in lower) else "world_sprite"
    else:
        art_domain = "none"

    # 4. Multi-agent flag
    multi_agent = True

    # 5. Extract significant keywords
    stopwords = {
        "the", "a", "an", "is", "in", "to", "for", "and", "or", "of", "with", "at",
        "by", "from", "up", "about", "into", "over", "after", "it", "this", "that",
        "these", "those", "all", "each", "every", "some", "any", "no", "not", "only"
    }
    tokens = re.findall(r'\b[a-zA-Z0-9_\-]{3,}\b', lower)
    keywords = [t for t in tokens if t not in stopwords][:12]

    # 6. Graph queries extraction
    graph_queries = []
    func_matches = re.findall(r'\b([a-zA-Z_]\w+)\s*\(', raw_prompt)
    for fm in func_matches:
        if fm not in graph_queries and fm not in ("print", "def", "if", "for", "while"):
            graph_queries.append(fm)

    for tf in target_files:
        stem = Path(tf).stem
        if stem and stem not in graph_queries and len(stem) > 2:
            graph_queries.append(stem)

    if not graph_queries:
        graph_queries = [k for k in keywords if len(k) > 4][:2]

    # 7. Intent summary
    intent = raw_prompt.strip().split("\n")[0][:160]

    return {
        "raw_prompt": raw_prompt,
        "intent": intent,
        "task_category": task_category,
        "art_domain": art_domain,
        "multi_agent": multi_agent,
        "keywords": keywords,
        "target_files": target_files,
        "graph_queries": graph_queries[:3]
    }


def execute_graphify_queries(
    graph_queries: List[str],
    repo_root: Path,
    timeout: float = 10.0
) -> Dict[str, Any]:
    """Runs graphify query for up to 3 queries using python_exe in graphify-out/.graphify_python, with fallback."""
    results: Dict[str, Any] = {}
    py_path_file = repo_root / "graphify-out" / ".graphify_python"
    py_bin = None
    if py_path_file.is_file():
        try:
            cand = py_path_file.read_text(encoding="utf-8").strip()
            if cand and Path(cand).is_file():
                py_bin = cand
        except Exception:
            pass

    for q in graph_queries[:3]:
        q_clean = q.strip().strip('"').strip("'")
        if not q_clean:
            continue
        success = False
        if py_bin:
            try:
                proc = subprocess.run(
                    [py_bin, "-m", "graphify", "query", q_clean],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8"
                )
                if proc.returncode == 0:
                    stdout = proc.stdout.strip()
                    lines = stdout.splitlines()
                    summary_line = lines[0] if lines else f"Graph query for '{q_clean}' completed."
                    nodes_found = []
                    for line in lines[1:]:
                        if line.startswith("NODE "):
                            parts = line.split()
                            if len(parts) > 1:
                                nodes_found.append(parts[1])
                    results[q_clean] = {
                        "summary": summary_line,
                        "nodes": nodes_found[:10],
                        "total_nodes": len(nodes_found),
                        "source": "cli"
                    }
                    success = True
            except Exception:
                success = False

        if not success:
            graph_json_file = repo_root / "graphify-out" / "graph.json"
            if graph_json_file.is_file():
                try:
                    gdata = json.loads(graph_json_file.read_text(encoding="utf-8", errors="ignore"))
                    matched_nodes = []
                    q_lower = q_clean.lower()
                    for node in gdata.get("nodes", []):
                        nid = str(node.get("id", ""))
                        nlabel = str(node.get("label", ""))
                        if q_lower in nid.lower() or q_lower in nlabel.lower():
                            matched_nodes.append(nid)
                    results[q_clean] = {
                        "summary": f"Fallback graph.json lookup: {len(matched_nodes)} nodes match '{q_clean}'",
                        "nodes": matched_nodes[:10],
                        "total_nodes": len(matched_nodes),
                        "source": "graph.json_fallback"
                    }
                except Exception as ex:
                    results[q_clean] = {
                        "summary": f"Graph lookup error: {str(ex)}",
                        "nodes": [],
                        "total_nodes": 0,
                        "source": "error"
                    }
    return results


def extract_graph_neighbors(target_files: List[str], repo_root: Path) -> List[str]:
    """Extracts adjacent nodes from graphify-out/graph.json for any target files."""
    neighbors: List[str] = []
    graph_file = repo_root / "graphify-out" / "graph.json"
    if not graph_file.is_file() or not target_files:
        return neighbors
    try:
        gdata = json.loads(graph_file.read_text(encoding="utf-8", errors="ignore"))
        links = gdata.get("links", [])
        for tf in target_files:
            norm_tf = tf.replace("\\", "/").replace("res://", "")
            for link in links:
                s = str(link.get("source", ""))
                t = str(link.get("target", ""))
                if norm_tf in s and t not in neighbors:
                    neighbors.append(t)
                elif norm_tf in t and s not in neighbors:
                    neighbors.append(s)
    except Exception:
        pass
    return neighbors[:10]


def classify_task_tier(
    raw_prompt: str,
    target_files: List[str]
) -> Tuple[str, str, List[str]]:
    """Calculates tier (minor-doc, minor-visual, minor-logic, major) and recommended checks."""
    major_keywords = [
        "autoload", "architecture", "rewrite", "overhaul", "migration", "multiplayer",
        "state machine", "core refactor", "system rewrite", "upgrade engine"
    ]
    lower_task = raw_prompt.lower()
    is_major = any(re.search(r"\b" + re.escape(w) + r"\b", lower_task) for w in major_keywords) or len(target_files) > 2

    if target_files and all(f.endswith(".md") or f.endswith(".txt") for f in target_files):
        tier = "minor-doc"
        change_class = "Minor"
        verification_commands = ["python game.py clean --audit --json"]
    elif any(f.endswith(".tscn") for f in target_files) and not is_major:
        tier = "minor-visual"
        change_class = "Minor"
        first_tscn = next((f for f in target_files if f.endswith(".tscn")), "")
        verification_commands = [
            f"python game.py syntax --scan {first_tscn} --json" if first_tscn else "python game.py syntax --scan . --json",
            "python game.py baseline --check --json",
            f"python game.py capture --scene {first_tscn} --json" if first_tscn else "python game.py capture --json"
        ]
    elif not is_major:
        tier = "minor-logic"
        change_class = "Minor"
        verification_commands = [
            "python game.py syntax --scan . --json",
            "python game.py test --changed --json"
        ]
    else:
        tier = "major"
        change_class = "Major"
        verification_commands = [
            "python game.py syntax --scan . --json",
            "python game.py test --json",
            "python game.py capture --all-scenes --json",
            "python game.py validate --engine --json"
        ]
    return tier, change_class, verification_commands


def _recover_ps_stripped_json(raw: str) -> Optional[Dict[str, Any]]:
    """
    Recovers structured fields from PowerShell-mangled JSON strings where quotes
    were stripped by shell argument parsing:
    e.g. {raw_prompt: text, intent: ..., task_category: planning, art_domain: none, multi_agent: true, keywords: [a, b], target_files: [c], graph_queries: [d]}
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    inner = s[1:-1].strip()
    pattern = re.compile(
        r'(?:^|[,{\s])(?:"|\')?(raw_prompt|intent|task_category|art_domain|multi_agent|keywords|target_files|graph_queries)(?:"|\')?\s*:\s*',
        re.IGNORECASE
    )
    matches = list(pattern.finditer(inner))
    if not matches:
        return None

    result: Dict[str, Any] = {}
    for i, m in enumerate(matches):
        key = m.group(1).lower()
        val_start = m.end()
        val_end = matches[i + 1].start() if i + 1 < len(matches) else len(inner)
        raw_val = inner[val_start:val_end].strip()
        if raw_val.endswith(","):
            raw_val = raw_val[:-1].strip()

        if key in ("keywords", "target_files", "graph_queries"):
            list_val = raw_val
            if list_val.startswith("[") and list_val.endswith("]"):
                list_val = list_val[1:-1].strip()
            items = []
            if list_val:
                for item in list_val.split(","):
                    cleaned = item.strip().strip("'\"")
                    if cleaned:
                        items.append(cleaned)
            result[key] = items
        elif key == "multi_agent":
            lv = raw_val.lower().strip("'\"")
            result[key] = lv in ("true", "1", "yes")
        elif key in ("task_category", "art_domain"):
            result[key] = raw_val.strip().strip("'\"").lower()
        else:
            result[key] = raw_val.strip().strip("'\"")
    return result


def parse_payload(
    payload: Union[str, Dict[str, Any], None] = None,
    payload_file: Optional[Union[str, Path]] = None,
    payload_b64: Optional[str] = None
) -> Dict[str, Any]:
    """Parses payload from dict, string, file, or base64 with PowerShell stripped JSON recovery."""
    if payload_file:
        pf = Path(payload_file)
        if not pf.is_file():
            pf = REPO_ROOT / payload_file
        if pf.is_file():
            try:
                content = pf.read_text(encoding="utf-8")
                try:
                    return json.loads(content)
                except Exception:
                    rec = _recover_ps_stripped_json(content)
                    if rec:
                        return rec
                    return auto_dissect_prompt(content)
            except Exception as ex:
                return auto_dissect_prompt(str(ex))
    if payload_b64:
        try:
            decoded = base64.b64decode(payload_b64.strip()).decode("utf-8")
            try:
                return json.loads(decoded)
            except Exception:
                rec = _recover_ps_stripped_json(decoded)
                if rec:
                    return rec
                return auto_dissect_prompt(decoded)
        except Exception as ex:
            return auto_dissect_prompt(str(ex))
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        payload_str = payload.strip()
        if payload_str.startswith("{") and payload_str.endswith("}"):
            try:
                return json.loads(payload_str)
            except Exception:
                rec = _recover_ps_stripped_json(payload_str)
                if rec:
                    return rec
                return auto_dissect_prompt(payload_str)
        return auto_dissect_prompt(payload_str)
    return {}


def route_prompt(
    payload: Union[str, Dict[str, Any], None] = None,
    raw_prompt: Optional[str] = None,
    payload_file: Optional[Union[str, Path]] = None,
    payload_b64: Optional[str] = None,
    root: Optional[Union[str, Path]] = None,
    run_graphify: bool = True,
    write_audit: bool = True,
    files: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Deterministic 3-Layer Prompt-to-Skill & Graphify Router for Godot Dynamic Harness.
    """
    repo_root = Path(root).resolve() if root else REPO_ROOT
    skills_root = repo_root / ".agents" / "skills"

    # Load / dissect payload
    dissected = parse_payload(payload=payload, payload_file=payload_file, payload_b64=payload_b64)

    if not dissected and raw_prompt:
        dissected = auto_dissect_prompt(raw_prompt)

    if not dissected:
        dissected = auto_dissect_prompt("Default Godot task")

    if files:
        target_files = list(dissected.get("target_files") or [])
        for f in files:
            if f and str(f) not in target_files:
                target_files.append(str(f))
        dissected["target_files"] = target_files

    # Normalize dissected fields
    p_raw = str(dissected.get("raw_prompt") or dissected.get("intent") or "Godot task")
    p_intent = str(dissected.get("intent") or p_raw[:120])
    p_category = str(dissected.get("task_category") or "coding").lower()
    p_art = str(dissected.get("art_domain") or "none").lower()
    p_multi_agent = bool(dissected.get("multi_agent", True))
    p_keywords = list(dissected.get("keywords") or [])
    p_target_files = list(dissected.get("target_files") or [])
    p_graph_queries = list(dissected.get("graph_queries") or [])

    # Tracking match reasons and ordered skills
    matched_skills: List[str] = []
    skill_match_reasons: Dict[str, str] = {}

    # Discover skills present on disk
    dynamic_skills = discover_disk_skills(skills_root)
    available_disk_skills = set(dynamic_skills.keys())
    if skills_root.is_dir():
        for d in skills_root.iterdir():
            if d.is_dir():
                available_disk_skills.add(d.name)

    # Layer 1: Core Always-On Skills
    # Dynamically find any project-specific context skill if moonveil-context is not on disk
    active_core_skills = list(CORE_SKILLS)
    if "moonveil-context" not in available_disk_skills:
        for dname in available_disk_skills:
            if dname.endswith("-context") and dname not in active_core_skills:
                active_core_skills.insert(0, dname)
                break

    layer1_skills: List[str] = []
    for s in active_core_skills:
        # Check if skill exists on disk
        if not available_disk_skills or s in available_disk_skills or (skills_root / s).is_dir():
            layer1_skills.append(s)
            if s not in matched_skills:
                matched_skills.append(s)
                skill_match_reasons[s] = "Layer 1 Core Skill (always active)"
        else:
            # Skill not found on disk: keep in match reason for transparency, do not crash
            skill_match_reasons[s] = f"Layer 1 Core Skill (omitted: not found on disk at {skills_root / s})"

    # Layer 2: Deterministic Conditional Mode Rules
    layer2_skills: List[str] = []
    if p_category in CODING_CATEGORIES:
        conditional_mode = "caveman_full"
        caveman_mode = "full"
        caveman_reason = f"Coding/verification task category '{p_category}'; caveman_mode enabled"
        for s, r in [
            ("caveman", "Layer 2 Mode: caveman_full for coding/bugfix/qa/tuning/refactor"),
            ("cavecrew", "Layer 2 Mode: worker delegation protocol"),
            ("ponytail", "Layer 2 Mode: smallest complete change")
        ]:
            if s not in layer2_skills:
                layer2_skills.append(s)
            if s not in skill_match_reasons:
                skill_match_reasons[s] = r
    elif p_category in PROSE_CATEGORIES:
        conditional_mode = "prose"
        caveman_mode = "off"
        caveman_reason = f"Prose/documentation task category '{p_category}'; normal prose required"
    else:
        conditional_mode = "prose"
        caveman_mode = "off"
        caveman_reason = f"Task category '{p_category}'; normal prose required"

    # Dual-Fidelity Art Split
    art_split = "none"
    ui_keywords = [
        "ui", "hud", "modal", "menu", "theme", "button", "panel", "font", "slot",
        "hotbar", "inventory_slot", "dialogue_box", "toast", "crafting_ui", "stylebox",
        "vector ui", "mockup", "profile_card"
    ]
    world_sprite_keywords = [
        "world_sprite", "sprite", "crop", "16x16", "32x32", "tile", "tileset", "boulder",
        "tree", "animal", "pixel-art", "pixel art", "ground item", "fomt", "mfomt"
    ]

    corpus_text = f"{p_raw} {p_intent} {' '.join(p_keywords)} {' '.join(p_target_files)}".lower()

    if p_art == "ui" or any(re.search(r'\b' + re.escape(w) + r'\b', corpus_text) for w in ui_keywords):
        art_split = "cozy-hd-ui"
        for s, r in [
            ("cozy-hd-ui", "Layer 2 Art Split: Flat 2D Cozy HD Vector UI token standards"),
            ("godot-ui-containers", "Layer 2 Art Split: Container layouts & responsiveness"),
            ("godot-ui-theming", "Layer 2 Art Split: StyleBoxTexture & UI theming")
        ]:
            if s not in layer2_skills:
                layer2_skills.append(s)
            if s not in skill_match_reasons:
                skill_match_reasons[s] = r
    elif p_art == "world_sprite" or any(re.search(r'\b' + re.escape(w) + r'\b', corpus_text) for w in world_sprite_keywords):
        art_split = "harvest-moon-sprite"
        for s, r in [
            ("harvest-moon-sprite", "Layer 2 Art Split: 16x16/32x32 FoMT pixel-art standards"),
            ("pixel-art-gen", "Layer 2 Art Split: Pixel art rendering pipeline"),
            ("image-bg-removal", "Layer 2 Art Split: Alpha background separation")
        ]:
            if s not in layer2_skills:
                layer2_skills.append(s)
            if s not in skill_match_reasons:
                skill_match_reasons[s] = r

    # Multi-Agent Wave Rule
    if p_multi_agent:
        for s, r in [
            ("token-budget", "Layer 2 Multi-Agent Wave: Context boundary & token optimization"),
            ("cavecrew", "Layer 2 Multi-Agent Wave: Lead-worker delegation protocol")
        ]:
            if s not in layer2_skills:
                layer2_skills.append(s)
            if s not in skill_match_reasons:
                skill_match_reasons[s] = r

    for s in layer2_skills:
        if s not in matched_skills:
            matched_skills.append(s)

    # Layer 3: Complete 46-Skill Keyword & Synonym Dictionary + Dynamic Discovery
    full_skill_dict = dict(SKILL_DICTIONARY)
    for d_name, d_kws in dynamic_skills.items():
        if d_name in full_skill_dict:
            full_skill_dict[d_name] = list(set(full_skill_dict[d_name] + d_kws))
        else:
            full_skill_dict[d_name] = d_kws

    layer3_matched: List[str] = []
    for skill_name, triggers in full_skill_dict.items():
        matched_trigger = None
        for trig in triggers:
            trig_clean = trig.lower()
            if " " in trig_clean or "-" in trig_clean or "_" in trig_clean:
                if trig_clean in corpus_text:
                    matched_trigger = trig
                    break
            else:
                if re.search(r'\b' + re.escape(trig_clean) + r'\b', corpus_text):
                    matched_trigger = trig
                    break
                elif len(trig_clean) >= 5 and trig_clean in corpus_text:
                    matched_trigger = trig
                    break
        if matched_trigger:
            layer3_matched.append(skill_name)
            if skill_name not in matched_skills:
                matched_skills.append(skill_name)
                skill_match_reasons[skill_name] = f"Layer 3 Keyword match: '{matched_trigger}'"

    # Verify every matched skill resolves to an existing .agents/skills/<name>/SKILL.md
    matched_skill_paths: List[str] = []
    verified_matched_skills: List[str] = []
    for s in matched_skills:
        skill_file = skills_root / s / "SKILL.md"
        if skill_file.is_file():
            verified_matched_skills.append(s)
            matched_skill_paths.append(f".agents/skills/{s}/SKILL.md")
        elif (skills_root / s).is_dir():
            verified_matched_skills.append(s)
            matched_skill_paths.append(f".agents/skills/{s}")
        else:
            # Mark missing skills gracefully without crashing
            skill_match_reasons[s] = f"{skill_match_reasons.get(s, '')} [NOT FOUND ON DISK: {skills_root / s}]".strip()

    # If skills directory exists on disk, filter matched_skills strictly to verified ones
    if skills_root.is_dir() and any(skills_root.iterdir()):
        matched_skills = verified_matched_skills
        layer1_skills = [s for s in layer1_skills if s in verified_matched_skills]
        layer2_skills = [s for s in layer2_skills if s in verified_matched_skills]
        layer3_matched = [s for s in layer3_matched if s in verified_matched_skills]

    # Active Graphify & Graph Neighbor Executor
    graphify_results = {}
    if run_graphify:
        graphify_results = execute_graphify_queries(p_graph_queries, repo_root)

    graph_neighbors = extract_graph_neighbors(p_target_files, repo_root)

    # Change classification
    tier, change_class, recommended_checks = classify_task_tier(p_raw, p_target_files)

    # Audit Trail Logging
    now = datetime.datetime.now(datetime.timezone.utc)
    raw_hash = hashlib.sha256(p_raw.encode("utf-8")).hexdigest()[:6]
    audit_id = f"rt-{now.strftime('%Y%m%d%H%M%S')}-{raw_hash}"

    if write_audit:
        try:
            log_dir = repo_root / ".agent-state" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "router_audit.jsonl"
            audit_entry = {
                "timestamp": now.isoformat(),
                "audit_id": audit_id,
                "prompt": p_raw[:250],
                "task_category": p_category,
                "art_domain": p_art,
                "conditional_mode": conditional_mode,
                "caveman_mode": caveman_mode,
                "art_split": art_split,
                "matched_skills": matched_skills,
                "matched_count": len(matched_skills),
                "tier": tier,
                "change_class": change_class,
                "target_files": p_target_files,
                "graph_queries": p_graph_queries
            }
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # Receipt markdown block
    graph_receipt_parts = []
    for q, q_res in graphify_results.items():
        cnt = q_res.get("total_nodes", len(q_res.get("nodes", [])))
        graph_receipt_parts.append(f"{q} ({cnt} hits)")
    graph_receipt_str = ", ".join(graph_receipt_parts) if graph_receipt_parts else f"{len(p_graph_queries)} queries -> {len(graph_neighbors)} neighbors"

    receipt_markdown = (
        f"> **Router & Skills Receipt** (audit_id: {audit_id}) | "
        f"**Skills**: [{', '.join(matched_skills)}] | "
        f"**Mode**: {conditional_mode} | "
        f"**Art Split**: {art_split} | "
        f"**Graphify**: <{graph_receipt_str}>"
    )

    return {
        "audit_id": audit_id,
        "dissected_prompt": dissected,
        "layer1_core_skills": layer1_skills,
        "layer2_skills": layer2_skills,
        "layer3_matched_skills": layer3_matched,
        "matched_skills": matched_skills,
        "matched_skill_paths": matched_skill_paths,
        "skill_match_reasons": skill_match_reasons,
        "conditional_mode": conditional_mode,
        "caveman_mode": caveman_mode,
        "caveman_reason": caveman_reason,
        "art_split": art_split,
        "tier": tier,
        "verification_tier": tier,
        "change_class": change_class,
        "recommended_checks": recommended_checks,
        "graphify_results": graphify_results,
        "graph_neighbors": graph_neighbors,
        "receipt_markdown": receipt_markdown
    }


# Backward-compatible aliases
route_prompt_payload = route_prompt


def main() -> int:
    """CLI entry point for tools/skill_router.py."""
    parser = argparse.ArgumentParser(description="Godot Dynamic Harness 3-Layer Prompt-to-Skill & Graphify Router")
    parser.add_argument("prompt", nargs="*", help="Raw prompt string or tokens")
    parser.add_argument("--prompt", dest="opt_prompt", help="Explicit prompt string")
    parser.add_argument("--payload", help="Dissected prompt JSON payload string")
    parser.add_argument("--payload-file", help="Path to JSON file containing prompt payload")
    parser.add_argument("--payload-b64", help="Base64 encoded JSON payload string")
    parser.add_argument("--files", nargs="*", default=[], help="Target files to include in classification")
    parser.add_argument("--no-graphify", action="store_true", help="Skip live graphify query execution")
    parser.add_argument("--no-audit", action="store_true", help="Skip writing to router_audit.jsonl")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON output")

    args = parser.parse_args()

    prompt_str = args.opt_prompt or (" ".join(args.prompt) if args.prompt else None)
    res = route_prompt(
        payload=args.payload,
        raw_prompt=prompt_str,
        payload_file=args.payload_file,
        payload_b64=args.payload_b64,
        root=REPO_ROOT,
        run_graphify=not args.no_graphify,
        write_audit=not args.no_audit,
        files=args.files
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(res["receipt_markdown"])
        print(f"Matched Skills ({len(res['matched_skills'])}): {res['matched_skills']}")
        print(f"Tier: {res['tier']} ({res['change_class']})")
        print(f"Checks: {res['recommended_checks']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
