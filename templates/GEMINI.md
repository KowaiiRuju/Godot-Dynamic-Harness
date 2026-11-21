# Gemini & Antigravity Runtime Guidelines (GDH v2)

`AGENTS.md` is canonical. Load core workflow skills on demand from `.agents/skills/{ui-mockup-pipeline,core-architecture,godot-test-qa,gdscript-migration,agent-coordination,token-budget}` and domain reference playbooks from `.agents/playbooks/`.

## 1. Built-In Mandatory Skill Activation & Anti-Drift Gate
- **Deterministic Task Planning (`plan-task`)**: Before editing any `.tscn`, `.gd`, or asset file, run `python game.py plan-task "<task>" --json --compact` OR directly read the required skill in `.agents/skills/<skill>/SKILL.md` (`required_skills`). Never skip governing skills or drift from intended architecture.
- **Major-Only Graphify**: Run `python game.py graph --query "<question>" --json --compact` or `graphify query` / `graphify update .` **ONLY for `major` cross-system changes** (`triage_category == "major"`, `skip_graphify == false`, `>2` files, autoloads, save/migration, multiplayer). Skip Graphify on `trivial_chat`, `quick_question`, and `minor_*` tasks.
- **Zero-Bloat Startup**: Never run `python game.py info --json` on startup. Read `.context/project_state.json` ONLY when a command returns `"ctx_stale": true`.

## 2. Dual-Workhorse Split & Naming Standard
- **Gemini 3.8 Flash** (`gemini-3.8-flash-low|medium|high`; `Model="flash"`): Mechanical docs, visual capture/QA, syntax/test runs, bounded single-file edits.
- **Gemini 4 Hydrogen / Pro** (`gemini-4-hydrogen-medium|high|xhigh`; `Model="inherit"` / `"pro"`): Analytical reasoning (architecture, planning, review, tradeoffs, root-cause, race/desync debugging) and `major` cross-system work.
- **Prefix-First Naming**: `invoke_subagent(Role="<model>-<Think> <Worker>")` (e.g., `3.8-flsh-Med UI Builder`, `4-hyd-High Arch Review`); `swarm` / `game.py lock` slugs `<model_slug>-<think>-<role>` (`38flsh-med-ui`, `4hyd-high-arch`).

## 3. Single-Worker Lock Bypass, 5-Stage UI Mockup Pipeline & CLI Standard
- **Single-Worker Lock Bypass**: Skip `python game.py lock acquire` (`core/tools/agent_lock.py`) when working as a single writer (`multi_agent == false`). Acquire leases and record SHA-256 `write-off` entries only when `>= 2` concurrent write workers run in `swarm`.
- **User Art Style Prompt Gate & 5-Stage Connected UI Mockup Pipeline**:
  - **Stage 0 (Style & Prerequisites)**: Check `art_style_direction` in `.context/project_state.json` or `docs/art/style_guide.md`. If unset (`ask_user_art_style: true`), **explicitly ask the user to decide and define their art & UI style direction first** before generating mockups or assets. Use Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`) for mockups and UI assets, then check `python game.py mockup-dissect --check-prereqs --json --compact` and `python game.py assets --audit --json --compact`.
  - **Stage 1 (Dissect & Profile)**: `python game.py mockup-dissect --scene <scene.tscn> --mockup <mockup.png> --json --compact --out artifacts/ui_pipeline/dissect.json` -> writes `artifacts/ui_pipeline/dissection_manifest.json` & `manifest.json`.
  - **Stage 2 (Scene-First `.tscn` Authoring)**: Author `StyleBoxTexture` / `StyleBoxFlat` margins, `content_margin_*`, and container layout in `.tscn` (never `Control.new()` in GDScript) -> verify via `python game.py validate --uid --json --compact`.
  - **Stage 3 (Deterministic Grading)**: `python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact --out artifacts/ui_pipeline/grade.json` -> fix all `failed_components` until `passed: true`.
  - **Stage 4 (Visual Capture & Baseline Diff)**: `python game.py capture --scene <scene.tscn> --json --compact --out .agent-state/capture.json` -> `python game.py baseline --check --json --compact`.
- **UTF-8 CLI & Capture Discipline**: Always pass `--json --compact --out <filepath>` to `game.py` (never PowerShell `>` or `Out-File`). Passing commands emit `"next_command": null` so non-visual tests never auto-chain `capture`.
