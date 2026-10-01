# Harness Rules — IDE-Agnostic

These rules apply **regardless of which IDE or agent is running** (Antigravity,
Cursor, VS Code, Claude Code, Codex, Windsurf). Put this file in your agent's
context in any way your tool supports.

## Before Editing Anything

1. Run `python game.py handoff load`. If a previous agent left state, follow its
   Next Steps. Do not start over.
2. Run `python game.py info` to confirm the engine and tools resolve.
3. Run `python game.py lint`. A scene that fails lint will not load in game.
4. Read `AGENTS.md`. It is binding.

## Never

- Build UI in GDScript. No `Button.new()`, `Label.new()`, `Control.new()`,
  `add_theme_stylebox_override()`. UI lives in `.tscn`.
- Add a second Godot runner. Extend `core/tools/scene_runner.gd` or
  `scripts/testing/visual_test_runner.gd` and expose it through `game.py`.
- Edit `.tscn` `PackedByteArray` payloads by hand. Use the Godot editor.
- Trust a green exit code without checking for `SCRIPT ERROR` in the output.
- Delete skills or rules to "clean up" without checking whether a project
  feature depends on them.
- Commit `.harness/state.json`, `screenshots/debug/`, or `.godot/` by accident.
  They belong in `.gitignore`.

## Verification Ladder

Run these in order; stop at the first failure.

| Step | Command | Proves |
| :-- | :-- | :-- |
| 1 | `python game.py lint` | Scene files are structurally valid |
| 2 | `python game.py syntax --scan .` | No Godot 3.x syntax |
| 3 | `python game.py validate` | UI obeys the Scene-First rule |
| 4 | `python game.py sweep` | Every scene loads |
| 5 | `python game.py test` | Test suites pass |
| 6 | `python game.py capture --scene res://<x>.tscn` | It renders |
| 7 | `python game.py audit` | The layout is sane |
| 8 | view the PNG | It looks right |

Steps 1-5 are cheap and headless. Step 6 opens a hidden window. Step 8 is the
only one that catches "technically valid, visually wrong".

## Headless vs Capture

- `--headless` **disables rendering**. Use it for `lint`, `sweep`, `test`,
  `syntax`, `validate`.
- Capture uses `--rendering-method gl_compatibility --audio-driver Dummy` with an
  isolated `APPDATA`. Never pass `--headless` to a capture; the PNG will be blank.

## Quota Ran Out Mid-Task

Before switching agents or IDEs:

```bash
python game.py handoff save --task "what you were doing" \
    --next "the next concrete step" --next "the one after" --verify
```

Then in the new IDE:

```bash
python game.py handoff load
```

That prints the task, git state including uncommitted files, and next steps.
The JSON at `.harness/state.json` is the machine-readable version — read it
directly if you are driving this from a script.

## When Switching Agents, Do Not

- Reinstall skills. They live in `.agents/skills/` and are shared.
- Regenerate `AGENTS.md` from a template. It is project-specific.
- Start a parallel implementation. Check `git status` first; the other agent
  may have left work in progress.