---
name: gdscript-migration
description: Godot 4.x GDScript static typing, Signal Up / Call Down architecture, scene-outline navigation before reading .tscn, syntax --scan, and validate --uid. Load when writing, migrating, reviewing, or scanning .gd scripts.
---

# GDScript 4.x Standards & Migration Workflow (GDH v2)

## 1. Godot 4.x Syntax & Static Typing
- Target the project's detected Godot 4.x engine version and renderer in `.context/project_state.json`.
- Type variables, parameters, and return types explicitly (`var speed: float = 120.0`, `func get_count() -> int:`). Use typed arrays (`Array[Resource]`, `Array[Node]`) where applicable.
- Never use Godot 3 syntax (`yield`, `export var`, `onready var`, `connect("sig", target, "method")`, ` KinematicBody2D`). Use `await`, `@export`, `@onready`, `sig.connect(callable)`, and `CharacterBody2D`/`CharacterBody3D`.

## 2. Signal Up, Call Down & Lifecycle Hygiene
- **Signal Up, Call Down**: Child nodes emit typed `signal` declarations; parent containers or controllers connect to child signals and invoke child methods directly.
- **Node References**: Use `%SceneUniqueNames` or `@onready var` bound to nodes authored in `.tscn`. Never call `get_node()` or `find_child()` inside `_process()` or `_physics_process()`.
- **Scene-First UI**: Never instantiate UI controls procedurally (`Control.new()`, `Button.new()`, `Label.new()`, `Panel.new()`) in GDScript.
- **UTF-8 No BOM**: All `.gd`, `.tscn`, and `.tres` files must be saved as UTF-8 without BOM.

## 3. CLI Inspection & Verification
1. **Inspect `.tscn` Hierarchy Before Reading Raw Scene Files**:
   ```powershell
   python game.py scene-outline <scene.tscn> --json --compact --out .agent-state/outline.json
   ```
2. **Scan GDScript for 4.x Migration & Syntax Hints**:
   ```powershell
   python game.py syntax --scan <path> --json --compact --out .agent-state/syntax.json
   ```
3. **Validate Scene References, UIDs & Policy Rules**:
   ```powershell
   python game.py validate --uid --json --compact --out .agent-state/validate.json
   ```
