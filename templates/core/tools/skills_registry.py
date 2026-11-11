#!/usr/bin/env python3
"""Skills registry and curation engine for Godot agentic workspaces."""
import re
from pathlib import Path

REPOSITORIES = {
    "graphify": {
        "package": "graphifyy",
        "description": "Codebase AST knowledge graph & dependency queries (pip install graphifyy & graphify install)",
        "skills_subpath": "skill",
    },
    "gd_agentic_skills": {
        "url": "https://github.com/thedivergentai/GD-Agentic-Skills.git",
        "description": "Comprehensive Godot 4 domain skill library",
        "skills_subpath": "skills",
    },
    "ponytail": {
        "url": "https://github.com/DietrichGebert/ponytail.git",
        "description": "Anti-bloat, YAGNI and lean architecture rules",
        "skills_subpath": "skills/ponytail",
    },
    "prompt_master": {
        "url": "https://github.com/nidhinjs/prompt-master.git",
        "description": "Meta-prompt optimization and agent prompt tuning",
        "skills_subpath": ".",
    },
    "caveman": {
        "url": "https://github.com/JuliusBrussee/caveman.git",
        "description": "Conditional ultra-compressed communication & subagent token-saving suite (caveman, cavecrew, caveman-compress)",
        "skills_subpath": "skills",
    },
    "bundled": {
        "url": None,
        "description": "Bundled GDH harness core skill",
        "skills_subpath": ".",
    },
}

CORE_SKILLS = [
    "graphify",
    "ponytail",
    "prompt-master",
    "agent-coordination",
    "token-budget",
    "godot-master",
    "godot-gdscript-mastery",
    "godot-project-foundations",
    "godot-signal-architecture",
    "godot-autoload-architecture",
    "godot-scene-management",
    "godot-resource-data-patterns",
    "godot-ui-containers",
    "godot-ui-theming",
    "godot-testing-patterns",
]

SKILL_SPEC_MAP = {
    "graphify": ("graphify", "skill"),
    "ponytail": ("ponytail", "skills/ponytail"),
    "prompt-master": ("prompt_master", "."),
    "caveman": ("caveman", "skills/caveman"),
    "cavecrew": ("caveman", "skills/cavecrew"),
    "caveman-compress": ("caveman", "skills/caveman-compress"),
    "i-have-adhd": ("caveman", "skills/i-have-adhd"),
    "image-bg-removal": ("caveman", "skills/image-bg-removal"),
    "agent-coordination": ("bundled", "agent-coordination"),
    "token-budget": ("bundled", "token-budget"),
    "godot-agent-vision": ("bundled", "godot-agent-vision"),
    "pixel-art-gen": ("bundled", "pixel-art-gen"),
}


def get_skill_spec(name: str):
    if name in SKILL_SPEC_MAP:
        repo_key, subpath = SKILL_SPEC_MAP[name]
        repo_info = REPOSITORIES[repo_key]
        return {
            "name": name,
            "repo_key": repo_key,
            "repo_url": repo_info.get("url"),
            "package": repo_info.get("package"),
            "repo_subpath": subpath,
        }
    return {
        "name": name,
        "repo_key": "gd_agentic_skills",
        "repo_url": REPOSITORIES["gd_agentic_skills"]["url"],
        "package": None,
        "repo_subpath": f"skills/{name}",
    }


def detect_project_traits(root: Path, context: dict = None) -> dict:
    traits = {
        "is_2d": False,
        "is_3d": False,
        "is_mobile": False,
        "has_dialogue": False,
        "has_inventory": False,
        "has_quests": False,
        "has_save": False,
        "has_combat": False,
        "has_multiplayer": False,
        "has_shaders": False,
        "has_particles": False,
        "has_audio": False,
        "has_navigation": False,
        "has_state_machine": False,
        "has_procedural": False,
    }
    context = context or {}
    settings = context.get("authored_settings", {})

    # Check orientation / features / viewport
    features = [str(f).lower() for f in settings.get("features", [])]
    if "mobile" in features:
        traits["is_mobile"] = True

    vp_w = settings.get("viewport_width")
    vp_h = settings.get("viewport_height")
    if vp_w and vp_h and vp_h > vp_w:
        traits["is_mobile"] = True

    if not root.is_dir():
        return traits

    # Scan scene and script files (up to depth 4, max 100 files to stay fast)
    scan_count = 0
    patterns = {
        "2d": re.compile(r"\b(Node2D|CharacterBody2D|TileMap|TileMapLayer|Area2D|CollisionShape2D|Sprite2D)\b"),
        "3d": re.compile(r"\b(Node3D|CharacterBody3D|GridMap|Area3D|CollisionShape3D|MeshInstance3D|Camera3D)\b"),
        "dialogue": re.compile(r"(dialogue|dialog|textbox|conversation|speech)", re.I),
        "inventory": re.compile(r"(inventory|item_slot|item_data|equipment|loot)", re.I),
        "quests": re.compile(r"(quest|objective|mission|task_manager)", re.I),
        "save": re.compile(r"(save_load|savegame|game_state_save|user://.*\.save)", re.I),
        "combat": re.compile(r"(hitbox|hurtbox|health_component|damage|attack)", re.I),
        "multiplayer": re.compile(r"\b(MultiplayerSpawner|MultiplayerSynchronizer|ENetMultiplayerPeer|rpc|rpc_id|multiplayer)\b", re.I),
        "shaders": re.compile(r"\b(ShaderMaterial|VisualShader|\.gdshader|shader_type)\b", re.I),
        "particles": re.compile(r"\b(GPUParticles2D|CPUParticles2D|GPUParticles3D|CPUParticles3D)\b"),
        "audio": re.compile(r"\b(AudioStreamPlayer|AudioStreamPlayer2D|AudioStreamPlayer3D|AudioServer)\b"),
        "navigation": re.compile(r"\b(NavigationAgent2D|NavigationAgent3D|NavigationRegion2D|NavigationRegion3D|NavigationServer2D|NavigationServer3D|AStar2D|AStar3D|AStarGrid2D)\b"),
        "state_machine": re.compile(r"(state_machine|statemachine|fsm|finite_state|\bState\b)", re.I),
        "procedural": re.compile(r"(procedural|procgen|dungeon_generator|wave_function_collapse|perlin|simplex|fastnoiselite)", re.I),
    }

    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in (".git", ".harness", ".agents", "screenshots", "qa-evidence") for part in path.parts):
                continue
            name_lower = path.name.lower()
            if path.suffix in (".tscn", ".gd", ".gdshader"):
                scan_count += 1
                if scan_count > 100:
                    break
                content = ""
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    pass

                if patterns["2d"].search(content):
                    traits["is_2d"] = True
                if patterns["3d"].search(content):
                    traits["is_3d"] = True
                if patterns["dialogue"].search(name_lower) or patterns["dialogue"].search(content):
                    traits["has_dialogue"] = True
                if patterns["inventory"].search(name_lower) or patterns["inventory"].search(content):
                    traits["has_inventory"] = True
                if patterns["quests"].search(name_lower) or patterns["quests"].search(content):
                    traits["has_quests"] = True
                if patterns["save"].search(name_lower) or patterns["save"].search(content):
                    traits["has_save"] = True
                if patterns["combat"].search(name_lower) or patterns["combat"].search(content):
                    traits["has_combat"] = True
                if patterns["multiplayer"].search(name_lower) or patterns["multiplayer"].search(content):
                    traits["has_multiplayer"] = True
                if patterns["shaders"].search(name_lower) or patterns["shaders"].search(content):
                    traits["has_shaders"] = True
                if patterns["particles"].search(name_lower) or patterns["particles"].search(content):
                    traits["has_particles"] = True
                if patterns["audio"].search(name_lower) or patterns["audio"].search(content):
                    traits["has_audio"] = True
                if patterns["navigation"].search(name_lower) or patterns["navigation"].search(content):
                    traits["has_navigation"] = True
                if patterns["state_machine"].search(name_lower) or patterns["state_machine"].search(content):
                    traits["has_state_machine"] = True
                if patterns["procedural"].search(name_lower) or patterns["procedural"].search(content):
                    traits["has_procedural"] = True
    except OSError:
        pass

    # Default to 2D if neither found
    if not traits["is_2d"] and not traits["is_3d"]:
        traits["is_2d"] = True

    return traits


def curate_skills(root: Path, context: dict = None, mode: str = "curated", caveman_mode: str = "conditional") -> list:
    if mode == "none":
        return []

    selected = {}

    def add_skill(name: str, rationale: str):
        if name not in selected:
            spec = get_skill_spec(name)
            spec["rationale"] = rationale
            selected[name] = spec

    for name in CORE_SKILLS:
        add_skill(name, "Core Godot & Agentic foundations (always retained)")

    if caveman_mode in ("conditional", "always"):
        add_skill("caveman", f"Token-efficient communication ({caveman_mode} mode)")
        add_skill("cavecrew", "Token-compressed subagents for targeted investigations and edits")
        add_skill("caveman-compress", "Memory file and natural language token compression")
        add_skill("i-have-adhd", "High-clarity next-action ADHD focus and single-runner reuse")

    if mode == "core":
        return sorted(selected.values(), key=lambda s: s["name"])

    traits = detect_project_traits(root, context)

    if traits["is_2d"]:
        add_skill("godot-characterbody-2d", "2D character physics and movement detected")
        add_skill("godot-2d-physics", "2D collision and physics detected")
        add_skill("godot-2d-animation", "2D sprite animations detected")
        add_skill("godot-tilemap-mastery", "2D tilemap world building detected")
        add_skill("image-bg-removal", "2D sprite background isolation and alpha defringing")

    if traits["is_3d"]:
        add_skill("godot-physics-3d", "3D physics detected")
        add_skill("godot-3d-lighting", "3D spatial lighting detected")
        add_skill("godot-3d-materials", "3D PBR materials detected")
        add_skill("godot-3d-world-building", "3D environment and gridmaps detected")

    if traits["is_mobile"]:
        add_skill("godot-platform-mobile", "Mobile target platform or touch resolution detected")
        add_skill("godot-adapt-desktop-to-mobile", "Mobile responsive layout rules")

    if traits["has_dialogue"]:
        add_skill("godot-dialogue-system", "Dialogue or conversation components detected")

    if traits["has_inventory"]:
        add_skill("godot-inventory-system", "Inventory, equipment, or item system detected")

    if traits["has_quests"]:
        add_skill("godot-quest-system", "Quest or objective tracking detected")
        add_skill("godot-rpg-stats", "RPG stat progression and attributes detected")

    if traits["has_save"]:
        add_skill("godot-save-load-systems", "Save/load serialization system detected")

    if traits["has_combat"]:
        add_skill("godot-combat-system", "Hitbox/hurtbox or combat mechanics detected")

    if traits["has_multiplayer"]:
        add_skill("godot-multiplayer", "Multiplayer synchronization or RPC detected")

    if traits["has_shaders"]:
        add_skill("godot-shaders", "Shaders or visual materials detected")

    if traits["has_particles"]:
        add_skill("godot-particles", "Particle systems detected")

    if traits["has_audio"]:
        add_skill("godot-audio-architecture", "AudioStreamPlayer or audio buses detected")

    if traits["has_navigation"]:
        add_skill("godot-navigation-2d" if traits["is_2d"] else "godot-navigation-3d", "Navigation and pathfinding detected")

    if traits["has_state_machine"]:
        add_skill("godot-state-machines", "Finite state machine patterns detected")

    if traits["has_procedural"]:
        add_skill("godot-procedural-generation", "Procedural generation or noise patterns detected")

    return sorted(selected.values(), key=lambda s: s["name"])
