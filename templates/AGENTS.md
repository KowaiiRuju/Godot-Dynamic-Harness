# Godot Agent Harness — Core Rules (GDH v2)

- **Dynamic Engine & Renderer Context**: Discover Godot 4.x version, viewport, renderer, and autoloads from `.context/project_state.json` (`docs/harness/PROJECT.md`).
- **Zero-Bloat Startup**: NEVER run `python game.py info --json` on startup; read `.context/project_state.json` ONLY when a command returns `"ctx_stale": true`.
- **CLI Standard**: Always run `python game.py <cmd> --json --compact --out <file>`. Never use PowerShell `>` or `Out-File` redirection (avoids UTF-16LE corruption).
- **Mandatory Skill Activation Gate**: BEFORE editing any `.tscn`, `.gd`, or asset file, run `python game.py plan-task "<task>" --json --compact` OR read the governing skill via `read_file` so you never skip skills or drift from intended features:
  | Task Domain | Governing Skill (`read_file` Before Editing) |
  | --- | --- |
  | UI / HUD / Modals / Mockups / Assets | `.agents/skills/ui-mockup-pipeline/SKILL.md` |
  | Architecture / Autoloads / Scene Wiring | `.agents/skills/core-architecture/SKILL.md` |
  | GDScript 4.x / Signals / Static Typing | `.agents/skills/gdscript-migration/SKILL.md` |
  | Testing / Captures / Baselines / QA | `.agents/skills/godot-test-qa/SKILL.md` |
  | Multi-Agent Swarm / File Leases (`lock`) | `.agents/skills/agent-coordination/SKILL.md` |
  | Context Boundaries / Bounded Line Reads | `.agents/skills/token-budget/SKILL.md` |
- **User-Chosen Art & UI Style Direction + Canva MCP**: Never hardcode Cozy HD or any fixed art style. If `art_style_direction` is unset in `.context/project_state.json` or `docs/art/style_guide.md`, **explicitly ask the user to decide and define their art & UI style direction first**, then use Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`) for mockups/assets (graded `>= 8.5` across Fit, Style, Composition) and follow the 5-stage `ui-mockup-pipeline`.
- **Scene-First & Inspector-First Policy**: Never build UI procedurally via `Control.new()` in GDScript; author all layout/StyleBoxes in `.tscn` (`scene-outline` before reading `.tscn`), expose tunables via `@export`, and use `y_sort_enabled = true` on top-down 2D sorting containers.
- **Proportionate Verification, Major-Only Graphify & Conditional Caveman**: Run targeted checks for `Minor` tasks and full regression + `game.py graph --refresh/--query` ONLY for `Major` tasks (`skip_graphify: true` on non-major tasks). Use `Caveman` (`full`/`lite`) + `cavecrew` for routine code/QA; switch to normal prose (`off`) for plans, docs, dialogue, and lore.
