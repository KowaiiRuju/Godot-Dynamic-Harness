---
name: core-architecture
description: Project-agnostic Godot 4.x architecture, dynamic autoload lookup via .context/project_state.json, Scene-First UI policy, User-Chosen Art/UI Style Direction, @export/Y-Sort standards, and multi-agent communication rules. Load before editing architecture, autoloads, or scene wiring.
---

# Core Architecture (GDH v2)

## 1. Dynamic Autoload & Project State Discovery
- **Never Hardcode Project Autoloads**: Read active autoload singletons, main scene, viewport dimensions, renderer, and engine version dynamically from `.context/project_state.json` (or `docs/harness/PROJECT.md`).
- **Zero-Bloat Refresh**: Only re-read `.context/project_state.json` or run `python game.py context --refresh --json --compact` when a command response reports `"ctx_stale": true`.

## 2. Scene-First & Inspector-First Standards
- **No Procedural UI**: Author all UI nodes, containers, fonts, themes, and `StyleBox` (`StyleBoxTexture` / `StyleBoxFlat`) resources inside `.tscn` / `.tres` files. NEVER call `Control.new()`, `Label.new()`, `Button.new()`, `Panel.new()`, `Container.new()`, or `TextureRect.new()` in GDScript.
- **Outline Before Reading `.tscn`**: Always run `python game.py scene-outline <scene.tscn> --json --compact` to inspect node paths, `%UniqueNames`, scripts, and signal connections before reading specific line ranges.
- **Inspector Exports**: Expose all tunable gameplay numbers (speeds, timers, thresholds, capacities, damages, offsets, scene references) via `@export`, `@export_group`, `@export_range`, and `@export_enum`.
- **2D Top-Down Y-Sort & Origins**: For top-down 2D sorting containers, set `y_sort_enabled = true`, align entity local origins `(0, 0)` to ground contact points, and keep visual shadows on separate child nodes/shaders outside physics collision shapes.

## 3. User-Chosen Art & UI Style Direction
- **Style-Agnostic Enforcement**: Never force a fixed aesthetic (such as Cozy HD or 16-bit pixel art) unless the user has chosen it.
- **Mandatory User Style Prompt Gate**: Check `art_style_direction` in `.context/project_state.json` and `docs/art/style_guide.md`. If unset, **explicitly ask the user to decide and define their art & UI style direction first**, record it, and follow `.agents/skills/ui-mockup-pipeline/SKILL.md`.

## 4. Multi-Agent Ownership & Communication Rules
- **Disjoint Ownership & Single-Worker Bypass**: Shared files (`project.godot`, autoloads, `game.py`) belong to the Lead Integrator. Skip `python game.py lock` when working alone (`multi_agent == false`); acquire file leases via `python game.py lock acquire` and record SHA-256 `write-off` entries only when `>= 2` concurrent write workers run in `swarm`.
- **ADHD Style (`i-have-adhd`)**: Lead with the concrete next action, number multi-step work, restate state, cap lists to 5 items, and omit filler preamble.
- **Conditional Caveman**: Use `caveman` concise output for `coding`, `bugfix`, `tuning`, `qa`, and `refactor`; switch to normal prose (`off`) for `planning`, architecture docs, dialogue, and lore.
