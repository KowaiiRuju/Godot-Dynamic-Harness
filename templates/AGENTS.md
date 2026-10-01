# Project Guidelines & Agent Instructions

## 1. Scene-First / Editor-First UI Construction
- **MANDATORY: READ `.tscn` FIRST**: Always read and inspect the `.tscn` scene file FIRST before writing or modifying any GDScript. The `.tscn` file is the ground truth.
- **NEVER BUILD UI IN GDSCRIPT CODE**: Do NOT instantiate UI elements dynamically in GDScript using `Control.new()`, `Button.new()`, `PanelContainer.new()`, `Label.new()`, `TextureRect.new()`, `HBoxContainer.new()`, or `VBoxContainer.new()`.
- **NEVER CREATE OR OVERRIDE STYLES IN CODE**: Do NOT create `StyleBoxFlat.new()` or call `add_theme_stylebox_override()`, `add_theme_font_size_override()`, `add_theme_color_override()`, etc. in GDScript.
- **ALL UI MUST BE VISUALLY EDITABLE IN GODOT EDITOR**:
  - Every screen, HUD, modal, card, inventory slot, grid item, list row, and button MUST be constructed directly in `.tscn` scene files with all containers, labels, styles, margins, anchors, and fonts pre-baked.
  - If a list or grid repeats items (e.g. inventory slots, dialogue choices, spell icons), create a dedicated `.tscn` component scene or pre-place the nodes in the parent scene so the developer can visually select and tweak every element in the Godot 2D/3D Canvas.
- **GDSCRIPT'S ONLY ROLE IN UI**: GDScript should ONLY assign runtime data (e.g. `label.text = player_name`, `texture_rect.texture = icon_tex`, `button.disabled = is_locked`), connect signals, and handle state/animation logic.

## 2. Godot Architecture: The Layer Cake
Organize game systems into four distinct layers:
1. **Presentation** (UI / HUD / VFX / Audio): Listens to signals, displays state. Never owns data or alters game state directly.
2. **Logic** (State Machines / Components / Systems): Queries data, manages state transitions and mechanics.
3. **Data** (`Resource` / `.tres`): Single serializable source of truth for stats, inventory items, quests, dialogue trees.
4. **Infrastructure** (Autoload singletons): Global managers (SaveManager, AudioBus, SignalBus). Communicates via "Signal Up, Call Down".

## 3. Ponytail YAGNI & Anti-Bloat Mandate
- Rely on Godot's built-in nodes (`Timer`, `PathFollow`, `VisibleOnScreenNotifier`, `NavigationAgent`) and typed GDScript functions before engineering custom framework layers.
- Do not build speculative abstractions or systems for features not yet requested.

## 4. ScrollContainer Mouse Filtering
- **Mouse Filter Pass in Scroll Views**: Always set `mouse_filter = 1` (Pass) or `mouse_filter = 2` (Ignore) for all Control nodes inside a `ScrollContainer`. This ensures that drag/scroll events are not consumed by child panels, buttons, or labels.

## 5. Heavy Compute & Planning Protocol
- **Implementation Plan Mandatory**: Before executing any multi-file refactoring, batch simulation, dataset generation, or heavy compute task, ALWAYS generate `implementation_plan.md` with `RequestFeedback: true` for user approval first.
