---
trigger: always_on
description: Strict repository directory boundaries, .agent-state/ concurrency isolation, .gdignore resource shielding, and tests/screenshots/ visual QA lifecycle.
---

# Directory Boundaries & Isolation Rules (GDH v2)

Strict repository directory boundaries, concurrency artifact isolation, engine import shielding, and QA screenshot lifecycles.

## 1. `.agent-state/` & `.context/` (Concurrency Leases, Journal & Hash-Gated State)
- **Purpose**: Local-only multi-agent orchestration, concurrency coordination, and hash-gated project state caching.
  - `.context/project_state.json`: Deterministic project metadata and `ctx_hash` cache (`art_style_direction`, `authored_settings`, `engine_version`).
  - `.agent-state/leases.json`: Active advisory file locks managed by `python game.py lock` (`core/tools/agent_lock.py`).
  - `.agent-state/journal.jsonl`: Append-only journal of completed writes with SHA-256 hashes.
  - `.agent-state/logs/<task-id>/<run-id>-<agent-id>.jsonl`: Agent progress and diagnostic logs.
- **Git Isolation**: `.agent-state/` and `.context/` are local-only, MUST be ignored by `.gitignore`, and NEVER committed to Git.
- **Engine Isolation**: Never store game scenes, scripts, or runtime resources inside `.agent-state/` or `.context/`.

## 2. `docs/` & `assets/ui/staging/` (Godot Resource Shielding)
- **Shielding Mandate**: Must contain a `.gdignore` file at the root of each folder (`docs/.gdignore`, `assets/ui/staging/.gdignore`).
- **Purpose**: Prevents the Godot engine from scanning, parsing, or generating `.import`/`.uid` files for design drafts, reference mockups, Markdown documentation, or staging assets.
- **Enforcement**: Any new staging or documentation directory added to the repository must immediately have `.gdignore` created within it.

## 3. `tests/screenshots/` (Visual QA Lifecycle)
- **Purpose**: Default output destination for visual test and capture runner screenshots (`python game.py capture` and `core/tools/scene_runner.gd`).
- **Pre-Run Purge**: Before executing a new capture run, `python game.py capture` automatically purges stale screenshots and `.import` artifacts in `tests/screenshots/`.
- **Post-Run Preservation**: Newly rendered PNG screenshots and `scene_manifest.json` are preserved after the run for user and agent inspection.
- **No Production Assets**: Never store permanent game textures or UI assets inside `tests/screenshots/`.

## 4. `core/tools/` (Automation Utility Standard)
- **Centralized Automation**: All shared CLI utilities, scripts, UI pipeline profilers (`core/tools/ui_pipeline/`), lock managers (`core/tools/agent_lock.py`), and linters live in `core/tools/` and are invoked through `python game.py`.
- **No Ad-Hoc Parallel Runners**: Do not create ad-hoc runner scripts at the repository root; extend or invoke `python game.py`.
