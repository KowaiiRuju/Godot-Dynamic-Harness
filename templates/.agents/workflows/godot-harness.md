---
name: godot-harness
description: Execute the 8-step Godot 4 Scene-First Dynamic Harness workflow
---

# Workflow: Godot Dynamic Harness

Execute the 8-step Godot 4 Scene-First development and verification lifecycle.

## Step 0: Pre-Flight Router & Task Plan
Run the unified skill and prompt router before reading or editing any project files:
```powershell
# Route prompt JSON or task description
python game.py route-prompt --payload-file <path_to_json> --json
# Or plan task directly from prompt
python game.py plan-task "<task_description>" --json
```

## Step 1: Skill Pre-Flight & Graphify Query
1. Call `read_file` on every path returned in `matched_skill_paths` (`.agents/skills/<skill>/SKILL.md`).
2. Query the knowledge graph for relevant nodes and relationships:
```powershell
graphify query "<feature_or_system>"
# Or inspect scene node hierarchy without raw file dumps
python game.py scene-outline <scene_path>
```
3. Report router receipt (`audit_id`, `Skills applied: [...]`, mode) in the handoff.

## Step 2: Change Classification & Advisory File Locking
1. Classify change as **Minor** (bounded, local, reversible) or **Major** (autoloads, save format, networking, core refactor, engine config).
2. When operating in a multi-agent squad (`multi_agent: true`), acquire advisory locks on all writable target files before modifying:
```powershell
python tools/agent_lock.py acquire <target_files...> --agent <agent_id> --task <task_id> --json
```

## Step 3: Scene-First & Inspector-First Implementation
Implement changes following Godot 4 Scene-First architecture standards:
- **Scene-First Mandate**: All UI elements, HUD bars, containers, buttons, labels, and actor trees MUST be authored in `.tscn` scene files. NEVER construct UI hierarchies dynamically in GDScript code using `.new()` and `add_child()`.
- **Inspector-First Parameters**: Expose all configurable gameplay parameters (speeds, timers, ranges, vitals, capacities) via `@export`, `@export_group`, `@export_range`, `@export_enum`. Never bury tunable numbers in private script constants.
- **GDScript Logic**: Bound to scene nodes via `%SceneUniqueNames` or `@onready var` strictly for logic, value updates, signals, and animations.
- **2D Sorting**: Top-down entities align sorting pivot with ground contact point; parent containers enable `y_sort_enabled = true`.

## Step 4: Proportionate Verification
Run checks based on the declared change classification:
```powershell
# Minor: targeted syntax check and focused test suite
python game.py syntax --scan <target_directory> --json
python game.py test --suite <test_suite_name> --json

# Visual/Scene verification: capture and inspect screenshots
python game.py capture --scene <scene_path> --json

# Major: full test, capture, and engine validation sweeps
python game.py test --json
python game.py capture --all-scenes --json
python game.py validate --engine --json
```

## Step 5: Write-Off & Context Refresh
1. Conclude all edits by recording SHA-256 hashes to the journal and releasing locks (when locks were acquired):
```powershell
python tools/agent_lock.py write-off <target_files...> --agent <agent_id> --summary "<concise_summary>" --json
```
2. Refresh the persistent context and project graph:
```powershell
python game.py context --refresh
graphify update .
```
