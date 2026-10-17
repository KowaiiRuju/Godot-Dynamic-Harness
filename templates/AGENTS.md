# Godot Development Workflow & Agent Architecture

## 1. Workhorse Model Fast-Start & Graphify-First Navigation
- **Deterministic Planning**: For incoming tasks, run `python game.py plan-task "<task description>" --json` to obtain change classification (`Minor` vs `Major`), Caveman routing, affected files, and linear step recipes.
- **Token-Capped Scene Inspection**: Never dump raw `.tscn` files into context. Run `python game.py scene-outline <scene.tscn> --json` to extract nodes, `%UniqueNames`, scripts, properties, and signal connections with line ranges. Then view only targeted lines.
- **Graphify Navigation**: Before codebase investigations, run `python game.py graph --json`. Refresh stale graphs with `python game.py graph --refresh --timeout 120 --json`, then query scoped dependencies using `python game.py graph --query "<question>" --json`. Verify graph findings against source code.
- **Fresh Sessions**: Start fresh sessions with `docs/harness/PROJECT.md`, `TOOLS.md`, and `CHECKPOINT.md`, then run `python game.py info --json`. Keep `docs/harness/CHECKPOINT.md` compact (< 2 KB).

## 1a. Autonomous Safe Execution
- Once an implementation plan or task is approved by the user, execute all planned phases autonomously end-to-end. Do not interrupt with repeated confirmation prompts for routine edits or checks. Stop only for genuine blockers, irreversible actions, or critical forks.

## 1b. Proportionate Test Selection (Minor vs Major)
- **Minor Changes** (1–2 files, localized bugfix, tuning values, UI tweak): Run targeted sanity checks: `python game.py syntax --scan <files> --json`, targeted test suite `python game.py test --suite <path> --json`, or `python game.py baseline --check --json`. Do NOT run 90-scene batch capture sweeps for minor edits.
- **Major Changes** (architectural refactor, scene tree overhaul, core physics, engine migration): Run full regression verification: `python game.py test --json`, `python game.py capture --all-scenes --json`, and `python game.py validate --engine --json`.

## 1c. Conditional Caveman Protocol (`https://github.com/JuliusBrussee/caveman.git`)
- **USE Caveman (`full` or `lite`) + `cavecrew` Subagents** when the task does **NOT** require heavy writing:
  - Routine code/scene edits, bug fixes, `@export` exposure, physics/collision tuning, test/capture commands, and codebase lookups.
  - Drop filler, drop articles, keep technical substance exact. Saves ~65% output and context tokens.
- **DO NOT USE Caveman (`off` / Normal Prose)** when the task **requires writing or rich explanation**:
  - `implementation_plan.md`, architecture/GDD documentation, in-game dialogue/quest/lore text, UI copywriting, user requests to "explain" or "walk me through", git commit/PR bodies for humans, and safety/irreversible warnings.

## 2. Scene-First UI & Inspector-First Architecture
- **Scene-First UI**: Never build user interfaces procedurally with `Control.new()` or `StyleBoxFlat.new()`. Construct `.tscn` scene hierarchies with built-in Godot Containers, Themes, and reusable PackedScenes. Bind signals and dynamic data in GDScript.
- **Inspector-First Gameplay Tuning**: All configurable speeds, timers, thresholds, damages, vitals, capacities, offsets, and scene references MUST be editable in the Godot Inspector. Expose them with `@export`, `@export_group`, `@export_range`, and `@export_enum`. Never hide gameplay numbers in private script constants.
- **2D Top-Down Y-Sort & Origins (When Applicable)**: In 2D top-down scenes with depth sorting, entity local origins `(0, 0)` should align with ground contact points. Enable `y_sort_enabled = true` on parent sorting containers. Expose sprite offsets or `Node2D.y_sort_origin` in Inspector. Visual shadows must be separate child nodes/shaders, never baked into collision shapes.

## 3. ADHD Communication & Single-Runner Reuse
- **i-have-adhd Directness**: Lead with the concrete next action. Number multi-step work. Suppress tangents. Restate state every turn. Cap lists to 5 items.
- **Single-Runner Tool Reuse**: Never author ad-hoc runner scripts. Reuse the unified `python game.py` CLI tools (`plan-task`, `scene-outline`, `test`, `capture`, `baseline`, `audit`, `assets`, `saves`, `validate`, `clean`).
- **Prune Capture Evidence**: Purge ephemeral debug captures using `python game.py clean --captures --json` before milestone completion or commits.

## 4. Visual Assets & Provider-Agnostic Workflow
- **Canva MCP & Local Tools**: Use Canva MCP when available (`--canva-mcp optional|enabled`). When Canva MCP is absent, fallback to local PIL / `transparent-background` via `python game.py assets --process`.
- **3-Tier Asset Grading Rubric**: Every asset must score >= 8.5 on:
  1. **Fit on Game (1–10)**: Theme, perspective, scale harmony.
  2. **Style (1–10)**: Palette compliance, crisp outlines, no blurry AI fringe.
  3. **Composition (1–10)**: Readable silhouette, clean alpha channel.
