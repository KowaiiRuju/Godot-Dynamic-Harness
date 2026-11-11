# Project Guidelines & Agent Instructions: Godot Dynamic Harness

This document defines the universal architectural standards, Scene-First authoring laws, 8-step agentic workflow, and tool execution protocol for any Godot 4.x project equipped with the **Godot Dynamic Harness (GDH)**.

---

## 1. Scene-First / Editor-First UI & Node Construction

- **MANDATORY: READ `.tscn` FIRST**: Always read and inspect the `.tscn` scene file FIRST before writing or modifying any GDScript. The `.tscn` file is the ground truth.
- **NEVER BUILD UI IN GDSCRIPT CODE**: Do NOT instantiate UI elements dynamically in GDScript using `Control.new()`, `Button.new()`, `PanelContainer.new()`, `Label.new()`, `TextureRect.new()`, `HBoxContainer.new()`, or `VBoxContainer.new()`.
- **NEVER CREATE OR OVERRIDE STYLES IN CODE**: Do NOT create `StyleBoxFlat.new()`, `StyleBoxTexture.new()`, or call `add_theme_stylebox_override()`, `add_theme_font_size_override()`, `add_theme_color_override()`, etc. in GDScript.
- **ALL UI MUST BE VISUALLY EDITABLE IN GODOT EDITOR**:
  - Every screen, HUD, modal, card, inventory slot, grid item, list row, and button MUST be constructed directly in `.tscn` scene files with all containers, labels, styles, margins, anchors, and fonts configured in the scene.
  - If a list or grid repeats items (e.g. inventory slots, dialogue choices, spell icons), create a dedicated `.tscn` component scene or pre-place the nodes in the parent scene so the developer can visually select and tweak every element in the Godot Canvas.
- **GDSCRIPT'S ONLY ROLE IN UI**: GDScript should ONLY assign runtime data (e.g. `label.text = player_name`, `texture_rect.texture = icon_tex`, `button.disabled = is_locked`), connect signals, and handle state/animation logic.

---

## 2. Mandatory Inspector-Editable Nodes & Attributes

- **Expose Tunables via `@export`**: Expose all configurable gameplay parameters (movement speeds, cooldowns, timers, ranges, vitals, capacities) via `@export`, `@export_group`, `@export_range`, `@export_enum`. Never bury tunable numbers in private script constants.
- **Explicit 2D Y-Sorting**: Parent sorting containers MUST have `y_sort_enabled = true`. 2D top-down entities MUST align their sorting pivot with their ground contact point (`y_sort_origin` or `Sprite2D` offset).

---

## 3. The 8-Step Godot Dynamic Harness Workflow

Every agent task follows this deterministic, disciplined execution lifecycle:

| Step | Phase | Action & CLI Command |
| :--- | :--- | :--- |
| **0** | **Pre-Flight Router & Task Plan** | Run `python game.py route-prompt --prompt "<task>" --json` or `python game.py plan-task "<task>" --json` to classify intent and extract target files. |
| **1** | **Skill Pre-Flight & Graph Query** | Call `read_file` on all returned `matched_skill_paths`. Query relationships via `graphify query "<feature>"` or inspect hierarchy with `python game.py scene-outline <scene>`. |
| **2** | **Change Classification & Locks** | Classify as **Minor** or **Major**. When `multi_agent: true`, acquire file leases via `python tools/agent_lock.py acquire <files...> --agent <id> --task <task_id> --json`. |
| **3** | **Scene-First Implementation** | Implement UI in `.tscn` hierarchies. Write GDScript bound to `%SceneUniqueNames` or `@onready`. Follow Ponytail YAGNI principles. |
| **4** | **Proportionate Verification** | Minor: run targeted `python game.py syntax` and `python game.py test`. Major: run full test, capture, and engine validation sweeps. |
| **5** | **Visual Verification** | Render offscreen pixel-perfect snapshots via `python game.py capture --scene <scene>` (uses isolated APPDATA profile; never conflicts with open Editor). |
| **6** | **Write-Off & Journaling** | Conclude edits by logging SHA-256 hashes: `python tools/agent_lock.py write-off <files...> --agent <id> --summary "<summary>" --json`. |
| **7** | **Context & Graph Refresh** | Refresh project context via `python game.py context --refresh` and update AST graph via `graphify update .`. |

---

## 4. Change Classification & Proportionate Verification

Before editing code, declare:
`Change class: Minor or Major | Reason: <scope and risk> | Verification: <specific checks>`

- **Minor**: Bounded, reversible adjustment without changing contracts, save formats, networking, core logic, or build configs.
  - *Verification*: `python game.py syntax --scan <dir> --json`, `python game.py test --changed --json`, or targeted scene capture.
- **Major**: Critical or cross-system changes (save/persistence, networking/auth, autoload singletons, world-gen, broad refactoring).
  - *Verification*: Full test suite `python game.py test --json`, all-scene capture `python game.py capture --all-scenes --json`, and engine validation `python game.py validate --engine --json`.

---

## 5. The 15 Unified `game.py` CLI Subcommands

The harness provides a single zero-dependency CLI runner (`game.py`) at the project root covering the full development and QA lifecycle:

| Subcommand | Description & Primary Use Case |
| :--- | :--- |
| **`info`** | Displays detected Godot executable, engine version, renderer, viewport dimensions, and discovered tests. |
| **`route-prompt`** | 3-Layer deterministic prompt-to-skill and mode router with audit logging in `.agent-state/logs/router_audit.jsonl`. |
| **`plan-task`** | Single-command prompt routing + structured task plan synthesis with affected files and test ladders. |
| **`scene-outline`** | Fast scene node hierarchy and Control layout inspection without dumping massive raw `.tscn` text. |
| **`capture`** | Offscreen viewport snapshot rendering to PNG via isolated QA profile (never crashes open Godot Editor). |
| **`baseline`** | Golden visual screenshot regression testing and pixel diff comparison. |
| **`test`** | Discovers and executes headless GDScript test suites under `tests/test_*.gd`. |
| **`validate`** | Static scene integrity, broken `ExtResource` paths, and procedural UI anti-pattern checks. |
| **`assets`** | Asset catalog scan, texture atlas tracking, and orphaned asset detection. |
| **`audit`** | Control node layout audit (bounding boxes, clipping, and font sizes via `scene_manifest.json`). |
| **`saves`** | Inspect, validate, backup, or wipe persistent save state files in `user://`. |
| **`syntax`** | Validates GDScript against Godot 3.x vs 4.x deprecations, and learns project-specific syntax memory. |
| **`graph`** | AST-driven knowledge graph queries, neighbor traversal, and concept explanations via Graphify. |
| **`context`** | Generates or refreshes persistent project context markdown and architecture summaries. |
| **`clean`** | Cleans orphaned temporary files, debug screenshots, and stale QA caches. |

---

## 6. Architecture: The Godot Layer Cake

Organize game systems into four strictly decoupled layers:
1. **Presentation** (UI / HUD / VFX / Audio): Listens to signals, displays state. Never owns data or alters game state directly.
2. **Logic** (State Machines / Components / Controllers): Queries data, manages state transitions and mechanics.
3. **Data** (`Resource` / `.tres`): Single serializable source of truth for stats, inventory items, quests, dialogue trees.
4. **Infrastructure** (Autoload singletons): Global managers (SaveManager, AudioBus, SignalBus). Communicates via "Signal Up, Call Down".

---

## 7. Multi-Agent Concurrency & Advisory File Locking (`tools/agent_lock.py`)

When multiple agents or parallel subagents collaborate:
- **Acquire Lease Before Writing**:
  ```powershell
  python tools/agent_lock.py acquire <files...> --agent <agent_id> --task <task_id> --json
  ```
- **Disjoint Writable Paths**: Multi-agent tasks operate on strictly non-overlapping writable paths. Shared entry points (`project.godot`, autoload singletons, `game.py`) belong exclusively to the Lead agent.
- **Yield on Collision**: If a lock collision occurs, halt the affected slice immediately and report the conflict to the lead. Never bypass locks.
- **Write-Off Changes**:
  ```powershell
  python tools/agent_lock.py write-off <files...> --agent <agent_id> --summary "<summary>" --json
  ```

---

## 8. Ponytail YAGNI & Anti-Bloat Mandate

- Rely on Godot's built-in nodes (`Timer`, `PathFollow2D`/`3D`, `VisibleOnScreenNotifier`, `NavigationAgent`) and typed GDScript functions before engineering custom framework layers.
- Avoid speculative abstractions or systems for features not yet requested.
- Controls inside any `ScrollContainer` must set `mouse_filter = 1 (Pass)` or `2 (Ignore)` so dragging is never swallowed.
