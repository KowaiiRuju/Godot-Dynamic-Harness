# Harness Rules — IDE-Agnostic

These rules apply **regardless of which IDE or agent is running** (Google Antigravity, Cursor, VS Code, Claude Code, Codex, Windsurf). Put this file in your agent's context in any way your tool supports.

---

## 1. Before Editing Anything (Pre-Flight Protocol)

1. **Check Previous State / Handoff**: Run `python game.py handoff load`. If a previous agent left state, follow its Next Steps. Do not start over.
2. **Pre-Flight Route & Plan**:
   ```bash
   python game.py route-prompt --prompt "<task_description>" --json
   # or
   python game.py plan-task "<task_description>" --json
   ```
3. **Verify Environment**: Run `python game.py info` to confirm engine and tools resolve.
4. **Structural Scene Check**: Run `python game.py validate`. A scene that fails validation will not load in game.
5. **Read Binding Rules**: Read `AGENTS.md`. It is binding.

---

## 2. Never

- **Never build UI in GDScript**: No `Button.new()`, `Label.new()`, `Control.new()`, `add_theme_stylebox_override()`. UI lives in `.tscn`.
- **Never add a second Godot runner**: Extend `core/tools/scene_runner.gd` or `scripts/testing/visual_test_runner.gd` and expose it through `game.py`.
- **Never edit `.tscn` `PackedByteArray` payloads by hand**: Use the Godot editor or high-level scene utilities.
- **Never trust a green exit code without checking for `SCRIPT ERROR`**: Always inspect the tool output.
- **Never delete skills or rules to "clean up"**: Check whether a project feature depends on them first.
- **Never commit `.harness/state.json`, `.agent-state/leases.json`, `screenshots/debug/`, or `.godot/`**: Ensure they are in `.gitignore`.

---

## 3. The 8-Step Godot Dynamic Harness Workflow

Every modification follows the 8-step lifecycle:
1. **Pre-Flight Router**: Run `python game.py route-prompt` or `python game.py plan-task`.
2. **Skill Reads & Graph Query**: Read `matched_skill_paths`, query `graphify query "<feature>"`, or inspect nodes with `python game.py scene-outline <scene>`.
3. **Classification & Leases**: Declare `Change class: Minor or Major`. Acquire file leases via `python tools/agent_lock.py acquire` when multi-agent.
4. **Scene-First Implementation**: Build visual trees in `.tscn`. Expose tunables via `@export`. Bound GDScript to nodes via `%SceneUniqueNames`.
5. **Proportionate Verification**: Execute the verification ladder tailored to change classification.
6. **Visual Capture Verification**: Capture offscreen snapshots with `python game.py capture --scene <scene>`.
7. **Write-Off Journaling**: Release leases and commit SHA-256 hashes via `python tools/agent_lock.py write-off`.
8. **Context Refresh**: Update project context via `python game.py context --refresh` and run `graphify update .`.

---

## 4. Verification Ladder & The 15 `game.py` Commands

Run checks in order based on change classification; stop at the first failure.

| Step | Command | Proves |
| :--- | :--- | :--- |
| 1 | `python game.py syntax --scan .` | No deprecated Godot 3.x syntax or invalid constructs |
| 2 | `python game.py validate` | Scene files are structurally valid and obey Scene-First rule |
| 3 | `python game.py scene-outline <scene>` | Scene hierarchy and node layouts are correct |
| 4 | `python game.py test` | Headless GDScript test suites in `tests/` pass |
| 5 | `python game.py capture --scene res://<x>.tscn` | Offscreen rendering succeeds without crash |
| 6 | `python game.py audit` | Control node layout, bounding boxes, and fonts are sane |
| 7 | `python game.py baseline --check` | No unintended visual regressions against golden references |
| 8 | view the PNG in `screenshots/debug/` | Scene looks visually correct |

### Complete 15 `game.py` Command Reference
- `info`: Environment, Godot executable, renderer, viewport, and test discovery.
- `route-prompt`: 3-layer prompt router with dynamic skill matching and audit logging.
- `plan-task`: Single-command routing + actionable task plan generation.
- `scene-outline`: Fast scene hierarchy & Control node layout inspection without raw `.tscn` dumps.
- `capture`: Offscreen viewport snapshot rendering to PNG with isolated APPDATA QA profile.
- `baseline`: Golden visual screenshot regression testing and pixel diff comparison.
- `test`: Headless GDScript unit and integration test runner for `tests/test_*.gd`.
- `validate`: Static scene integrity, broken `ExtResource` paths, and procedural UI anti-pattern checks.
- `assets`: Asset database, texture atlas scan, and orphan detection.
- `audit`: Scene layout, bounding boxes, clipping, and font size inspection via `scene_manifest.json`.
- `saves`: Inspect, validate, or wipe persistent save state files in `user://`.
- `syntax`: Scan code for Godot 3.x vs 4.x syntax deprecations, or record newly learned patterns.
- `graph`: AST-driven knowledge graph queries and dependency traversal via Graphify.
- `context`: Generate or refresh persistent project context markdown and architecture summaries.
- `clean`: Remove orphaned temp files, debug screenshots, and stale QA caches.

---

## 5. Headless vs Capture Execution

- `--headless` **disables rendering completely**: Use it for `test`, `syntax`, `validate`, `clean`.
- **Capture uses an offscreen window**: Uses `--rendering-method gl_compatibility --audio-driver Dummy` with an isolated `APPDATA` directory (`<project>_godot_qa_profile`). Never pass `--headless` to a visual capture; the resulting PNG will be blank.

---

## 6. Quota Ran Out Mid-Task (Agent Handoff)

Before switching agents or IDEs:
```bash
python game.py handoff save --task "what you were doing" \
    --next "the next concrete step" --next "the one after" --verify
```

Then in the new IDE or turn:
```bash
python game.py handoff load
```

The JSON at `.harness/state.json` is the machine-readable version.
