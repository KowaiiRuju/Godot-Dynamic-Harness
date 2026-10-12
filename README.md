# Godot Dynamic Harness

A review-first toolkit that equips Godot developers and their IDE agents with project-aware Python tools and persistent project context. Antigravity is the first integration; VS Code is the second.

The core CLI uses the Python standard library. It resolves the selected Godot executable/version and project, exposes command capabilities as JSON, checks scenes/scripts, runs tests, renders captures, and maintains a source graph and Markdown guidance.

## Start with a plan

Clone this repository, then inspect your game without installing anything or starting its scenes/autoloads:

~~~powershell
python bootstrap.py plan --project "C:\Games\MyGame" --ide antigravity
~~~

Or use the PowerShell wrapper:

~~~powershell
.\setup.ps1 -Project "C:\Games\MyGame" -IDE antigravity
~~~

The result points to a Markdown plan containing exact file diffs, dependency actions, verification actions and conflicts, plus its matching JSON plan. Review it with your agent and adjust the options to your game. Planning writes only review artifacts.

- --ide antigravity, vscode, or both selects persistent IDE instructions.
- --godot selects an executable; otherwise existing GODOT4_BIN/GODOT_BIN, PATH, then an unambiguous Desktop executable are checked.
- --graphify existing uses the installed tool. If missing, regenerate with --graphify install to propose installation into the project's .harness/venv. Nothing is installed before approval.
- --graphify skip is an explicit opt-out; it does not satisfy the normal graph-navigation workflow.
- --smoke proposes a reusable main-scene smoke test and its execution after approval. Omit it when your game's initialization needs a tailored test.
- --png-grid proposes Pillow for PNG comparison sheets when it is unavailable. Installation uses only the project's .harness/venv; the wrapper option is -PNGGrid. HTML galleries work without Pillow.
- --skills curated, core, all, or none curates and deploys agent skills to .agents/skills/ (Graphify, Ponytail, Prompt-Master, and Godot domain skills) tailored to project dimension and mechanics. The CLI default is curated.
- --timeout sets the subprocess deadline.

After the user has explicitly approved that exact plan, run the apply command printed at its end:

~~~powershell
python bootstrap.py apply --plan "<JSON plan path>" --approve <approval digest>
~~~

The digest identifies the reviewed content; it cannot prove a human reviewed it. The agent must obtain approval in conversation first. Altered plans, changed source/project inputs, and conflicting custom tools require a new plan. Existing Markdown guidance is preserved around managed blocks. Custom game.py/core helpers are never silently replaced; conflicts need manual adoption/merging.

The approved setup installs selected files, refreshes project context, builds the source graph when selected, and runs only the selected smoke test. Dependency failures stop before toolkit writes. Verification failures remain visible even when files were installed. Re-running a plan does not repeat installations.

## What gets installed

| Path | Purpose |
| --- | --- |
| game.py | Discoverable CLI with text/JSON results |
| core/tools/ | Configuration probe, engine/resource checker, capture runner, migration notes and Godot graph adapter |
| AGENTS.md | Concise Godot development and review-first workflow |
| .agents/rules/godot-harness.md | Antigravity always-on workspace rule |
| .github/copilot-instructions.md | VS Code repository instructions, when selected |
| docs/harness/PROJECT.md | Engine, scene, viewport, renderer and autoload facts; room for project decisions |
| docs/harness/TOOLS.md | Actual commands, limits and evidence requirements |
| docs/harness/CHECKPOINT.md | Last tool outcome; room for session handoff notes |
| graphify-out/graph.json | Persistent local source graph |
| .harness/ | Plan approvals, freshness state, optional dependency environment and setup/check outcomes |
| tests/test_harness_smoke.gd | Optional main-scene smoke test |
| .agents/skills/ | Curated workspace agent skills with valid SKILL.md definitions |

Setup adds local graph/profile/venv/capture exclusions to .gitignore. Project guidance can be committed; generated graph/state stays local and survives IDE restarts.

## Fresh agent session

1. Read PROJECT.md, TOOLS.md, CHECKPOINT.md and the project's existing instructions.
2. Run python game.py info --json for actual engine/project/tool availability.
3. Before a codebase investigation, inspect graph status, refresh if needed, and make a scoped query.
4. Read the relevant source/scene to verify graph findings; make the requested change.
5. Run the relevant checks/capture, inspect returned findings/artifacts, refresh graph/context, and leave concise handoff notes outside managed blocks.

This avoids repeatedly explaining the game in each new chat. Instructions request the workflow; they do not technically prevent an agent from bypassing them.

## Tool calls

Run these inside the installed game's root. Common --project, --godot, --timeout and --json options work before or after the command.

~~~powershell
python game.py info --json
python game.py graph --json
python game.py graph --refresh --timeout 120 --json
python game.py graph --query "Main.tscn" --json
python game.py context --refresh --json
python game.py validate --json
python game.py validate --engine --json
python game.py syntax --scan . --json
python game.py syntax --query export --json
python game.py test --list --json
python game.py test --json
python game.py capture --json
python game.py capture --scene res://Main.tscn --width 720 --height 1280 --json
python game.py capture --scenes res://Menu.tscn res://Levels/Level01.tscn --json
python game.py capture --all-scenes --json
~~~

info lists command-specific arguments and prerequisites from the same registrations as argparse. JSON mode returns one document with schema_version, command, status, context, summary, findings and artifacts. Logs are separate on stderr. failed/unsupported/invalid input/timeout exit nonzero. skipped means no work ran; it is not a passed test.

Project configuration discovery runs in a scratch project and does not start target game code. Authored configuration, running engine version and effective rendering settings are distinct. Engine checks and test/capture commands execute project code and may write caches. Each engine call uses a separate user-data profile and preflights its save configuration without target autoloads; this is not a code sandbox.

Capture defaults to the configured main scene and effective viewport. It preserves the project renderer unless --renderer explicitly overrides it. It requires graphics support and may open a rendering window. Success requires a PNG and matching manifest; repeat/concurrent default captures have distinct artifact paths. Capture evidence is not gameplay or device acceptance.

Batch capture uses --scenes for a chosen set or --all-scenes for every discovered .tscn. It renders up to three scenes concurrently, keeps selection order, and continues after individual failures. Results include each scene's PNG/manifest, batch_results.json, a clickable gallery.html, and numbered PNG sheets with up to six scenes each in three columns. Images retain their aspect ratio without cropping. Failed scenes have labeled tiles and make the command exit nonzero. Without Pillow, the HTML gallery and individual images remain available, with an explicit PNG-export limitation.

Choose complete runnable scenes: isolated components may need parents, autoload state or setup data to display correctly. Each scene is captured after its initial layout/render frames; this does not automatically navigate gameplay or populate a menu. A scene path label identifies each tile, including scenes with identical filenames in different folders.

## Testing strategies: Smoke, sanity, and regression testing

The harness supports three progressive testing tiers (see [TESTING_GUIDE.md](docs/TESTING_GUIDE.md) and [TestingXperts Software Testing Types](https://www.testingxperts.com/blog/types-of-software-testing)):

1. **Smoke Testing (Build acceptance gate)**:
   - **Purpose**: Broad, shallow verification of project startup. Verifies Godot launches without crashing, `project.godot` loads, autoload singletons initialize, and the main scene instantiates cleanly.
   - **When to run**: After initial setup, engine version change, or before starting new feature development.
   - **Recipe**:
     ~~~powershell
     python game.py test --suite tests/test_harness_smoke.gd --json
     python game.py capture --json
     ~~~
   - **Rule**: If smoke tests fail, halt development immediately and resolve the launch/autoload crash.

2. **Sanity Testing (Focused feature & bug-fix check)**:
   - **Purpose**: Narrow, deep verification of a specific modified script, scene, or bug fix. Confirms the targeted behavior is rational without executing all unrelated tests.
   - **When to run**: Immediately after editing a script or `.tscn` scene.
   - **Recipe**:
     ~~~powershell
     python game.py test --suite tests/test_specific_feature.gd --json
     python game.py capture --scene res://screens/TargetScene.tscn --json
     python game.py validate --engine --json
     ~~~

3. **Regression Testing (Comprehensive project verification)**:
   - **Purpose**: Exhaustive check ensuring recent changes did not break existing features, scene layouts, scoring logic, or engine compatibility.
   - **When to run**: Before pull requests, git commits, milestone exports, or after significant refactoring.
   - **Recipe**:
     ~~~powershell
     python game.py test --json                    # all discovered test suites
     python game.py capture --all-scenes --json     # visual UI regression check
     python game.py validate --engine --json        # engine parse/load check
     python game.py syntax --scan . --json          # GDScript version migration scan
     ~~~
   - Review `qa-evidence/batch-grid/gallery.html` and `contact_sheet_*.png` to spot visual container/anchor regressions across all scenes.

## Persistent Graphify navigation

The installed Graphify inspected during development did not natively parse GDScript or Godot scenes. This harness adds a source-located index for Godot function/signal/class declarations, scene nodes and explicit res:// resource references, then uses Graphify to query it. Project Python/C# files use Graphify's AST extraction; harness infrastructure is excluded from the game graph.

- Freshness uses source-content and graph digests across processes.
- Missing, stale or untracked graphs cannot be queried through the wrapper until refreshed.
- Query output has a hard character cap; Graphify's token-budget option is a hint, not exact token accounting.
- Dynamic paths, signal wiring, scene UID relationships, shaders and runtime behavior still need direct inspection.
- Existing untracked or modified graph content is preserved in .harness/graph-backups before adopting the managed graph; richer semantic content is not merged into this source index.
- Graph state persists on disk. Rules must still be tested in a real agent session; token savings have not been benchmarked.

## Migration notes and learning

syntax --scan provides applicable migration hints, not a GDScript compiler. validate scans policy and resource-reference hints; --engine adds native engine parsing and explicit resource-load checks. It uses existing import metadata rather than starting the editor importer. For assets/global classes needing import metadata, open the project in Godot first. Standalone editor --import hangs on this host's engine and is not counted as verified. Gameplay assertions belong in tests.

Learning a syntax note does not automatically make it authoritative. An active rule needs explicit reviewed provenance, numeric version bounds and a safe matcher:

~~~powershell
python game.py syntax --learn-syntax-old "old_api()" --learn-syntax-new "new_api()" --verified --min-version 4.0 --max-version-exclusive 4.8 --matcher call --literal old_api --source-url "https://docs.godotengine.org/en/4.7/"
~~~

That example illustrates the contract; do not add invented API rules to a real project. Matchers are escaped token/call/annotation patterns; arbitrary learned regex/code is not executed. Conflicting updates fail, writes are atomic, and concurrent learning uses an exclusive lock. Unverified/versionless legacy entries remain queryable notes.

## Verification and limits

~~~powershell
python -m unittest discover -s tests -p "test_*.py"
~~~

Core development was checked on Windows with Python 3.12, Godot 4.7.2 and the installed Graphify. Unit tests cover version fixtures; they do not prove runtime compatibility with other engines. Integration tests use disposable games, real engine/capture checks, reviewed setup, Graphify queries and fresh-process persistence.

Real Antigravity and VS Code agent-session compliance, Linux execution, additional real Godot versions and dependency installation over the network remain acceptance checks. Engine execution is explicitly unavailable on macOS/other platforms until an appropriate isolated profile is implemented; metadata discovery remains available. See [verification evidence](docs/VERIFICATION.md), [implementation plan](tasks/plan.md) and [checklist](tasks/todo.md).

The original copy/paste bootstrap is now a [review-first agent prompt](Godot_Dynamic_Harness_Prompt.txt). No bulk skill-library installation, destructive skill pruning, MCP server or live-editor controller is included.

## Official references

- [Godot command-line tools](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html)
- [Godot project settings](https://docs.godotengine.org/en/stable/classes/class_projectsettings.html)
- [Antigravity persistent workspace rules](https://www.antigravity.google/docs/rules/)
- [VS Code repository instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)

## License

[MIT](LICENSE).
