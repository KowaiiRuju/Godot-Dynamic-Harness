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
- **Explicit 2D Y-Sorting**: Parent sorting containers MUST have `y_sort_enabled = true`. 2D top-down entities MUST align their sorting pivot with their ground contact point (`y_sort_origin` or `Sprite2D` offset). Visual shadows must be separate child nodes/shaders, never baked into collision shapes.

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

## 5. Conditional Caveman Protocol (`https://github.com/JuliusBrussee/caveman.git`)

- **USE Caveman (`full` or `lite`) + `cavecrew` Subagents** when the task does **NOT** require heavy writing:
  - Routine code/scene edits, bug fixes, `@export` exposure, physics/collision tuning, test/capture commands, and codebase lookups.
  - Drop filler, drop articles, keep technical substance exact. Saves ~65% output and context tokens.
- **DO NOT USE Caveman (`off` / Normal Prose)** when the task **requires writing or rich explanation**:
  - `implementation_plan.md`, architecture/GDD documentation, in-game dialogue/quest/lore text, UI copywriting, user requests to "explain" or "walk me through", git commit/PR bodies for humans, and safety/irreversible warnings.

---

## 6. ADHD Communication & Single-Runner Reuse (`i-have-adhd`)

- **i-have-adhd Directness**: Lead with the concrete next action. Number multi-step work. Suppress tangents. Restate state every turn. Cap lists to 5 items.
- **Single-Runner Tool Reuse**: Never author ad-hoc runner scripts. Reuse the unified `python game.py` CLI tools (`route-prompt`, `plan-task`, `scene-outline`, `test`, `capture`, `baseline`, `audit`, `assets`, `saves`, `validate`, `clean`).
- **Prune Capture Evidence**: Purge ephemeral debug captures using `python game.py clean --captures --json` before milestone completion or commits.

---

## 7. Visual Assets & Provider-Agnostic Workflow

- **Canva MCP & Local Tools**: Use Canva MCP when available (`--canva-mcp optional|enabled`). When Canva MCP is absent, fallback to local PIL / `transparent-background` via `python game.py assets --process`.
- **3-Tier Asset Grading Rubric**: Every asset must score >= 8.5 on:
  1. **Fit on Game (1–10)**: Theme, perspective, scale harmony.
  2. **Style (1–10)**: Palette compliance, crisp outlines, no blurry AI fringe.
  3. **Composition (1–10)**: Readable silhouette, clean alpha channel.
