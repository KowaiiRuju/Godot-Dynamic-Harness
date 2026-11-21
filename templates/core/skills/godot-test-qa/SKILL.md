---
name: godot-test-qa
description: Proportionate change classification (Minor doc, Minor visual, Minor logic, Major), game.py --json --compact --out caching rules, headless validation, and visual capture hygiene. Load when running tests, QA, or verification.
---

# Godot Test & QA Workflow (GDH v2)

## 1. Proportionate Change Classification (Declare Before Editing)
- **Minor doc (`minor_doc`)**: Reread wording, verify diff. No headless Godot startup, no `game.py graph --refresh` (`skip_graphify: true`).
- **Minor visual (`minor_visual`)**: Render and inspect changed scene state via:
  `python game.py capture --scene <scene.tscn> --json --compact --out .agent-state/capture.json`
  and verify layout bounds via `python game.py baseline --check --scene <scene.tscn> --json --compact`.
- **Minor logic (`minor_logic`)**: Run targeted GDScript syntax and test suite checks:
  `python game.py syntax --scan <changed.gd> --json --compact --out .agent-state/syntax.json`
  `python game.py test --suite tests/test_<name>.gd --json --compact --out .agent-state/test_run.json`
- **Major (`major` — cross-system, autoloads, netcode, save/migration, >2 core files)**: Run full verification sweep:
  `python game.py test --json --compact --out .agent-state/test_all.json`
  `python game.py validate --engine --orphans --uid --json --compact --out .agent-state/validate.json`
  `python game.py syntax --scan . --json --compact --out .agent-state/syntax.json`
  `python game.py graph --refresh --timeout 120 --json --compact`

## 2. CLI Output & Prefix-Cache Rules
- Always pass `--json --compact --out <filepath>` to `python game.py` so outputs write directly in UTF-8 LF with normalized POSIX paths. NEVER use PowerShell `>` or `Out-File` redirection (which emit UTF-16LE).
- `--compact` emits `schema_version: 2` payloads that omit the 250-token `context` block whenever `ctx_stale == false`. Read `.context/project_state.json` only if `ctx_stale == true`.
- Successful logic and unit tests return `"next_command": null`; do NOT auto-chain `capture` after non-visual logic tests.

## 3. Visual Capture & Repository Hygiene
- `python game.py capture` automatically purges stale files in `tests/screenshots/` before rendering and preserves the fresh capture PNGs and manifests for user review.
- Run `python game.py clean --audit --json --compact` to detect orphan `.uid`/`.import` files, `.gdignore` violations, or expired multi-agent leases, and `python game.py clean --captures --json --compact` before commits.
