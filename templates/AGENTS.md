# Godot development workflow

- Inspect before setup. Present a tailored plan with exact file/dependency actions; wait for explicit user review/approval before applying it. Preserve existing rules, skills, settings and helpers.
- Start fresh sessions with docs/harness/PROJECT.md, TOOLS.md and CHECKPOINT.md, then run python game.py info --json. Refresh stale context using python game.py context --refresh --json.
- Before each codebase investigation, check python game.py graph --json, refresh missing/stale/untracked graphs with graph --refresh --timeout 120 --json, then graph --query "the investigation question" --json. Prefer scoped queries to loading the full graph/report. Verify graph findings against source. If Graphify fails, report why; a user-approved direct-source fallback must be recorded.
- After code/config changes, refresh graph and context. Tool outcomes update the checkpoint; add concise decisions, next steps and unverified assumptions outside its managed block. Never store secrets in guidance/checkpoints.
- Read relevant .tscn before changing attached GDScript. Author UI layout, themes and reusable components in editable scenes; bind data and signals in scripts. Instantiating a reusable PackedScene is valid. Pure engine/tool infrastructure has no UI scene requirement.
- Use the selected engine version and matching official documentation. Migration scans, engine parse/load checks, rendered captures, gameplay and device acceptance are separate evidence.
- Prefer typed GDScript, composition, child signals to parents and explicit dependencies. Adapt to existing architecture rather than imposing a new framework.
- Preserve clickable controls in scroll views; verify input propagation before changing mouse_filter. Do not apply a blanket filter rule.
- Discover arguments from info --json. Check status/findings/artifacts; skipped means no work ran. Engine checks/tests execute project code; isolated save data is not a sandbox.
- Propose game-specific helpers and skills only for demonstrated needs. Utilize curated agent skills under .agents/skills/ (Graphify, Ponytail, Prompt-Master, and Godot domain skills) tailored to the project during bootstrap; do not unreviewed bulk-install or destructively delete customized skills.
- Follow tiered testing strategies (see docs/TESTING_GUIDE.md):
  * Smoke Testing: After setup or engine updates, run python game.py test --suite tests/test_harness_smoke.gd --json or capture --json. If startup crashes or autoloads fail, stop immediately and fix the break before continuing.
  * Sanity Testing: After modifying a specific scene or script, run targeted sanity checks: python game.py test --suite <path> --json, capture --scene <path> --json, and validate --engine --json.
  * Regression Testing: Before marking tasks complete, committing code, or exporting builds, run full regression verification: python game.py test --json, capture --all-scenes --json, validate --engine --json, and syntax --scan . --json.
- Manage capture artifacts responsibly: Default captures in screenshots/debug/ automatically retain only the 5 most recent runs. Purge ephemeral debug captures and review galleries using python game.py clean --captures --json (or clean --all --json) before milestone handoffs or git commits.


