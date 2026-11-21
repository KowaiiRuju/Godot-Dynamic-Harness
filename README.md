# Godot Dynamic Harness (GDH v2)

A review-first, token-debloated toolkit that equips Godot 4 developers and their IDE agents (Antigravity and VS Code) with project-aware Python tools, hash-gated `.context/project_state.json` caching, mandatory skill activation gates, multi-agent advisory locking (`game.py lock`), and a style-agnostic 5-stage UI mockup pipeline.

The core CLI (`game.py`) uses the Python standard library. It resolves the selected Godot 4 executable/version and project, emits `schema_version: 2` ultra-compact JSON outputs (`--json --compact --out <file>`), checks scenes/scripts, runs proportionate tests, dissects and grades UI mockups against `.tscn` control bounds, renders captures, and maintains a Major-only Graphify knowledge graph.

---

## Start with a Reviewed Plan (or `--upgrade`)

Clone this repository, then inspect your game without installing anything or starting its scenes/autoloads:

~~~powershell
python bootstrap.py plan --project "C:\Games\MyGame" --ide antigravity --skills curated --caveman conditional --canva-mcp optional
~~~

To upgrade an existing harness installation in place (`game.py`, `core/tools/**`, `.agents/rules/**`, `.agents/skills/**`, `AGENTS.md`, `GEMINI.md`) or seed an explicit art & UI style direction:

~~~powershell
python bootstrap.py plan --project "C:\Games\MyGame" --ide antigravity --upgrade --art-style "Flat 2D Vector UI + 16x16 Top-Down Pixel Art"
~~~

Or use the PowerShell wrapper:

~~~powershell
.\setup.ps1 -Project "C:\Games\MyGame" -IDE antigravity
~~~

### Planning Flags
- `--ide antigravity|vscode|both`: Selects persistent IDE instructions.
- `--upgrade`: Allows `bootstrap.py` to update existing harness-managed files (`game.py`, `core/tools/**`, `.agents/rules/**`, `.agents/skills/**`) in place instead of halting on content conflicts.
- `--art-style "<description>"`: Persists the user's chosen art & UI style direction in `.context/project_state.json`. If left unset (`""`), `game.py plan-task` and `game.py mockup-dissect` prompt the agent to ask the user for their art & UI style direction before generating mockups or assets.
- `--skills curated|core|all|none`: Installs core workflow skills into `.agents/skills/` and routes external `gd_agentic_skills` reference playbooks into `.agents/playbooks/` so IDE system prompts stay lean and prefix-cache-stable.
- `--caveman conditional|always|off`: Configures token-efficient Caveman communication (`conditional` uses Caveman for code/QA and normal prose for plans/docs/lore).
- `--canva-mcp optional|enabled|disabled`: Configures Canva MCP integration for UI mockups and visual assets.
- `--graphify existing|install|skip`: Configures the persistent Godot + Graphify source graph.
- `--smoke`: Proposes an optional `tests/test_harness_smoke.gd` main-scene smoke test.
- `--png-grid`: Proposes optional Pillow installation in `.harness/venv` for PNG contact sheets and 1D scanline bezel profiling.
- `--godot <path>` & `--timeout <seconds>`: Selects a specific Godot 4 binary and subprocess timeout.

After reviewing and approving the generated plan in `tasks/godot-harness-setup-<id>.md`, apply it with its exact digest:

~~~powershell
python bootstrap.py apply --plan "<JSON plan path>" --approve <approval digest>
~~~

---

## What Gets Installed (GDH v2)

| Path | Purpose |
| --- | --- |
| `game.py` | Unified CLI with `schema_version: 2` `--json --compact --out <file>` support |
| `core/tools/` | Engine/resource probes, capture runner, asset inspector (`>= 8.5` rubric), migration database, Godot graph adapter, and `agent_lock.py` |
| `core/tools/ui_pipeline/` | Style-agnostic 5-stage UI pipeline tools (`bezel_profiler.py`, `control_bounds_probe.gd`, `mockup_dissect.py`, `mockup_grade.py`) |
| `AGENTS.md` & `GEMINI.md` | High-signal, prefix-cache-stable GDH v2 specification with Mandatory Skill Activation Table |
| `.context/project_state.json` | Hash-gated (`ctx_hash`) project metadata and `art_style_direction` cache (`sort_keys=True`) |
| `.agents/rules/` | Focused workspace rules: `directory_boundaries.md`, `graphify.md`, `canva_image_gen.md`, and `godot-harness.md` |
| `.agents/skills/` | Core actionable workflow skills (`ui-mockup-pipeline`, `core-architecture`, `godot-test-qa`, `gdscript-migration`, `agent-coordination`, `token-budget`, `graphify`, `cavecrew`, `caveman`) |
| `.agents/playbooks/` | External Godot 4 reference playbooks (`gd_agentic_skills`), separated from `.agents/skills/` to prevent every-turn prompt bloat |
| `docs/harness/` | Deterministic `PROJECT.md`, `TOOLS.md`, and timestamp-free `CHECKPOINT.md` (< 2 KB) |
| `docs/.gdignore` | Shields documentation and reference mockups from Godot resource importing |
| `graphify-out/graph.json` | Persistent local Godot + Python/C# source graph (queried/rebuilt on `Major` tasks only) |
| `.harness/` | Plan approvals, freshness state, asset manifest, layout baselines, and setup state |

---

## GDH v2 Architecture Highlights

### 1. Zero-Bloat Startup & `schema_version: 2` Compact Caching
- **Never run `python game.py info --json` on startup**: Commands compute an 8-character `ctx_hash` from `project.godot` (`st_mtime_ns:st_size:engine_version`) cached in `.context/project_state.json`.
- **Ultra-Compact Outputs (`--compact`)**: When `--compact` is passed (without `--full`), `game.py` emits `schema_version: 2` payloads (~180 bytes) containing `cmd`, `status`, `ctx_hash`, `ctx_stale`, `active_skill`, `summary`, `findings`, and `next_command`, omitting the 250-token `context` block whenever `ctx_stale == false`.
- **UTF-8 File Output (`--out <filepath>`)**: Always pass `--out <filepath>` instead of PowerShell `>` or `Out-File` redirection to guarantee UTF-8 LF JSON with normalized POSIX paths (`/`).
- **Prefix-Cache Determinism**: `docs/harness/CHECKPOINT.md` strips volatile `time_utc` timestamps and random temp paths (keeping timestamps strictly in local `.harness/checkpoint.json` and `.agent-state/journal.jsonl`), and all JSON/Markdown outputs use `sort_keys=True`.

### 2. Built-In Mandatory Skill Activation & Anti-Drift Gate
Before editing any `.tscn`, `.gd`, or asset file, run `python game.py plan-task "<task>" --json --compact` or read the governing skill in `.agents/skills/<skill>/SKILL.md`:

| Task Domain | Governing Skill (`read_file` Before Editing) |
| --- | --- |
| UI / HUD / Modals / Mockups / Assets | `.agents/skills/ui-mockup-pipeline/SKILL.md` |
| Architecture / Autoloads / Scene Wiring | `.agents/skills/core-architecture/SKILL.md` |
| GDScript 4.x / Signals / Static Typing | `.agents/skills/gdscript-migration/SKILL.md` |
| Testing / Captures / Baselines / QA | `.agents/skills/godot-test-qa/SKILL.md` |
| Multi-Agent Swarm / File Leases (`lock`) | `.agents/skills/agent-coordination/SKILL.md` |
| Context Boundaries / Bounded Line Reads | `.agents/skills/token-budget/SKILL.md` |

`plan-task` deterministically returns `triage_category`, `required_skills`, `matched_playbooks`, `skip_graphify` (`False` only for `major` tasks), and `art_style_check` (`ask_user_art_style: True` when UI/art tasks run without a configured `art_style_direction`).

### 3. Style-Agnostic 5-Stage Connected UI Mockup Pipeline
Never hardcode Cozy HD or any fixed art style. The UI pipeline adapts to any user-chosen aesthetic:
1. **Stage 0 (Prerequisites & User Art Style Gate)**: Check `art_style_direction` in `.context/project_state.json` / `docs/art/style_guide.md`. If unset, **ask the user to define their art & UI style direction first**. Generate/export reference mockups and assets via Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`), then check `python game.py mockup-dissect --check-prereqs --json --compact` and `python game.py assets --audit --json --compact`.
2. **Stage 1 (Dissect & Profile)**:
   ~~~powershell
   python game.py mockup-dissect --scene res://scenes/ui/Hud.tscn --mockup docs/art/hud_mockup.png --json --compact --out artifacts/ui_pipeline/dissect.json
   ~~~
   Runs `bezel_profiler.py` (1D scanline border/bezel/lip detector) + `control_bounds_probe.gd` (headless Godot control rect & StyleBox extractor) -> writes `artifacts/ui_pipeline/dissection_manifest.json` and `manifest.json`.
3. **Stage 2 (Scene-First `.tscn` Authoring)**: Edit `StyleBoxTexture` / `StyleBoxFlat` margins, `content_margin_*`, and containers in `.tscn` (never `Control.new()` in GDScript) -> verify via `python game.py validate --uid --json --compact`.
4. **Stage 3 (Deterministic Grading)**:
   ~~~powershell
   python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact --out artifacts/ui_pipeline/grade.json
   ~~~
   Grades all `styled_controls`, margins, inner padding, sibling intersections, and stat-bar alignments until `passed: true`.
5. **Stage 4 (Visual Capture & Baseline Diff)**:
   ~~~powershell
   python game.py capture --scene res://scenes/ui/Hud.tscn --json --compact --out .agent-state/capture.json
   python game.py baseline --check --scene res://scenes/ui/Hud.tscn --json --compact --out .agent-state/baseline.json
   ~~~

### 4. Multi-Agent Advisory Leases & SHA-256 Journaling (`game.py lock`)
- **Single-Worker Bypass**: Skip `game.py lock` when working as a single writer (`multi_agent == false`).
- **Multi-Agent Swarm Coordination**: When `>= 2` concurrent write workers run, use `python game.py lock` (`core/tools/agent_lock.py`):
  ~~~powershell
  python game.py lock acquire scenes/ui/hud.tscn --agent 38flsh-med-ui --task hud-polish --json --compact
  python game.py lock status --json --compact
  python game.py lock write-off scenes/ui/hud.tscn --agent 38flsh-med-ui --task hud-polish --summary "Updated StyleBoxTexture margins" --json --compact
  python game.py lock prune --json --compact
  ~~~
  `--agent vscode-user` claims human IDE priority over autonomous workers.

---

## CLI Command Reference

~~~powershell
python game.py plan-task "Polish HUD layout and health bar" --json --compact --out .agent-state/plan.json
python game.py scene-outline res://scenes/Player.tscn --json --compact --out .agent-state/outline.json
python game.py mockup-dissect --check-prereqs --json --compact
python game.py mockup-dissect --scene res://scenes/ui/Hud.tscn --mockup docs/art/mockup.png --json --compact --out artifacts/ui_pipeline/dissect.json
python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact --out artifacts/ui_pipeline/grade.json
python game.py lock status --json --compact
python game.py graph --json --compact
python game.py graph --refresh --timeout 120 --json --compact
python game.py graph --query "Main.tscn" --json --compact
python game.py validate --engine --orphans --uid --json --compact --out .agent-state/validate.json
python game.py audit --physics --exports --signals --perf --json --compact --out .agent-state/audit.json
python game.py assets res://assets/player.png --json --compact
python game.py assets --process res://assets/player.png --crop-alpha --scale 2 --json --compact
python game.py assets --grade res://assets/player.png --t1 9.0 --t2 8.5 --t3 9.0 --json --compact
python game.py baseline --save --scene res://Main.tscn --json --compact
python game.py baseline --check --scene res://Main.tscn --tolerance 1.0 --json --compact
python game.py syntax --scan . --json --compact
python game.py test --tier minor-logic --changed --json --compact --out .agent-state/test.json
python game.py capture --scene res://Main.tscn --json --compact --out .agent-state/capture.json
python game.py clean --audit --json --compact
python game.py clean --all --json --compact
~~~

---

## Verification

Run the automated unit and engine integration test suite:

~~~powershell
python -m unittest discover -s tests -v
~~~

## License

[MIT](LICENSE).
