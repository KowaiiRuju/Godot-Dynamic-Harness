# Dynamic tool-call implementation checklist

Plan: [plan.md](plan.md). User authorized execution after confirming the expanded scope.
Use Python standard-library `unittest`; do not add a test dependency.

## Task 1: Truthful command results

**Description:** Reuse the existing subprocess boundary and handlers to report invalid inputs, failed checks, missing work and timeouts. Add a small shared result representation for later JSON output.

**Acceptance criteria:**
- [x] Missing scan targets and validation violations fail; missing suites are an explicit skip, not a passing test count; query/learn child failures propagate.
- [x] Engine/Python calls have a timeout and actionable launch/error diagnostics; no raw traceback for expected user errors.
- [x] Handler results carry command/status/findings/artifacts consistently, preserving readable CLI output.

**Verification:** `python -m unittest discover -s tests -p "test_*.py"`; reproduce each failure in temporary files, including a fake executable that hangs and a child returning nonzero.

**Dependencies:** None. **Scope:** Medium, up to 3 files.
**Files:** `templates/game.py`, `templates/core/tools/docs_updater.py`, new `tests/test_game_cli.py`.

## Task 2: Project and engine discovery

**Description:** Resolve explicit and default project/engine choices, then read project settings with a scratch Godot configuration probe rather than launching the game.

**Acceptance criteria:**
- [x] Validate `project.godot` and executable selection; invalid explicit choices and ambiguous fallbacks fail with a correction hint.
- [x] Report actual full engine version/help capabilities separately from project version hints, plus main scene, viewport, renderer, features and autoload declarations.
- [x] Discovery invokes no target main scene/autoload; two projects and paths with spaces produce distinct correct context, with no stale state.

**Verification:** Unit fixtures for two projects, engine priority/versions, ambiguity and missing inputs; real `--version` probe plus a disposable Godot project whose autoload marker must not execute during discovery.

**Dependencies:** Task 1. **Scope:** Medium, up to 3 files.
**Files:** `templates/game.py`, new `templates/core/tools/project_probe.gd`, `tests/test_game_cli.py`.

## Task 3: Discoverable JSON tool calls

**Description:** Add `--json` to existing commands and capability discovery to `info`, using the same command registrations as the parser.

**Acceptance criteria:**
- [x] Each JSON-mode call emits one parseable versioned result document to stdout, including argument/launch errors; logs are separate and exit status matches result status.
- [x] `info --json` lists real command arguments, effective defaults, prerequisites, availability/reasons and mutating flags; render support can remain unverified.
- [x] Legacy CLI calls still parse; advertised commands/arguments match argparse and context refreshes when settings or engine choices change.

**Verification:** Unit tests parse stdout with `json.loads` for success/failure/skip/unsupported cases and compare discovery descriptors against the parser, including noisy child output and invalid arguments.

**Dependencies:** Tasks 1-2. **Scope:** Small, up to 2 files.
**Files:** `templates/game.py`, `tests/test_game_cli.py`.

## Checkpoint after tasks 1-3

- [x] All focused tests pass; old calls and new JSON discovery work.
- [x] Two project fixtures produce correct fresh context; missing/invalid work is never reported as a successful check.

## Task 4: Applicable syntax rules from data

**Description:** Reuse `load_changes`, `save_changes`, query and learn. Replace the hardcoded matcher chain and `Dynamic -> Latest` logic with validated version-scoped entries.

**Acceptance criteria:**
- [x] Approved matchable rules apply only within their engine-version range; style advice, unknown-version notes and migration findings are distinguishable from engine errors.
- [x] Learning an approved applicable rule affects the next scan; old records remain queryable, while vague/unverified entries carry an explicit reason for exclusion.
- [x] Invalid/duplicate/conflicting updates cannot corrupt or silently overwrite the file; writes are atomic, and learned inputs cannot execute code or arbitrary regex.

**Verification:** `python -m unittest discover -s tests -p "test_*.py"`; round-trip learn/query/scan across version fixtures, malformed JSON/update fixtures and string/comment/token-boundary cases.

**Dependencies:** Tasks 1-3. **Scope:** Medium, up to 4 files.
**Files:** `templates/core/tools/docs_updater.py`, `templates/core/tools/gdscript_version_changes.json`, `templates/game.py`, new `tests/test_docs_updater.py`.

## Task 5: Project-aware capture

**Description:** Let omitted arguments use the project main scene and viewport. Preserve renderer fidelity and prove successful output with isolated execution state.

**Acceptance criteria:**
- [x] Default scene/size come from the selected project; explicit valid overrides win; invalid scene paths or nonpositive dimensions fail before capture.
- [x] Actual rendering mode is reported; the project renderer is preserved unless explicitly overridden, and missing graphics/timeout cannot count as visual success.
- [x] Each call has distinct artifact/profile paths; PNG, directory and manifest failures fail; successful files match scene, dimensions and manifest metadata.

**Verification:** Real disposable-project capture at project defaults and 720x1280; inspect PNG/manifest, force write errors, run two calls concurrently and verify actual user-data paths for two projects. Record untested platforms explicitly.

**Dependencies:** Tasks 1-3. **Scope:** Medium, up to 4 files.
**Files:** `templates/game.py`, `templates/core/tools/scene_runner.gd`, `tests/test_game_cli.py`, new `tests/test_engine_integration.py`.

## Task 6: Tests and engine validation

**Description:** Recursively discover/select suites and add actual engine parse/load evidence without presenting migration pattern scans as compilation.

**Acceptance criteria:**
- [x] `info`, `test --list` and execution use the same deterministic recursive discovery; `--suite` accepts an unambiguous project-relative test path and rejects missing/outside paths.
- [x] Failed assertions/script errors and timeouts are failures even when an engine exit code alone is misleading; no discovered tests remain an explicit skip.
- [x] Engine parse/load findings and broken scene-resource references are separate from Scene-First policy/migration findings, with locations and tested scope in JSON.

**Verification:** Nested, selected, missing, assertion-failing and parse-failing disposable suites; valid/invalid scripts and broken-resource scenes run against the selected local engine. Do not label mocked version fixtures cross-version runtime proof.

**Dependencies:** Tasks 1-4. **Scope:** Medium, up to 3 files.
**Files:** `templates/game.py`, `tests/test_game_cli.py`, `tests/test_engine_integration.py`.

## Checkpoint after tasks 4-6

- [x] Version fixtures and rule update/scan tests pass.
- [x] Real capture artifacts and isolation are verified; forced artifact failures fail correctly.
- [x] Nested suites and engine checks work; unsupported or untested environments remain visible.

## Task 7: Agent instructions match available tools

**Description:** Update the README, bootstrap prompt and generated agent rules to use capability discovery and verified calls instead of assuming a fixed engine, skill count or universal headless rendering.

**Acceptance criteria:**
- [x] Agent workflow starts with `info --json`, chooses available tools, and checks result status/artifacts; examples match implemented arguments.
- [x] Explain migration scan versus engine validation, authored versus effective defaults, and rendered capture versus gameplay/release acceptance.
- [x] Preserve existing user rules/skills and document manual template adoption; do not instruct agents to delete skills based on guessed genre or overwrite customized harnesses.

**Verification:** Execute every documented CLI example on disposable fixtures; compare prompt claims with `--help`/capability output; run the full focused unit/integration suite once after documentation alignment.

**Dependencies:** Tasks 1-6. **Scope:** Medium, up to 3 files.
**Files:** `README.md`, `Godot_Dynamic_Harness_Prompt.txt`, `templates/AGENTS.md`.

## Task 8: Review-first bootstrap

**Description:** Replace unconditional bootstrap installation with a plan/apply workflow containing reviewable file contents and dependency actions.

**Acceptance criteria:**
- [x] Planning inspects project configuration without starting game code and writes only plan artifacts; user can select IDE, Graphify installation and a smoke test.
- [x] Applying requires the reviewed plan digest, rejects altered/stale plans or source/target conflicts before changing files, and never replaces user-owned files silently.
- [x] Re-running setup preserves customizations, reports already-installed tools, and records dependency/verification outcomes truthfully.

**Verification:** Standard-library bootstrap tests cover no-install planning, edited/stale plan rejection, both IDE adapters, existing instructions, failure and repeated apply.
**Dependencies:** Tasks 1-7. **Files:** new `bootstrap.py`, `setup.ps1`, new `tests/test_bootstrap.py`, `README.md`.

## Task 9: Persistent context and graph navigation

**Description:** Save concise project context, commands and verified checkpoints; provide graph freshness/query/update tools and IDE-specific persistent rules.

**Acceptance criteria:**
- [x] Antigravity and VS Code adapters require Graphify before investigations and load project overview/command/checkpoint context; missing/stale graphs and unavailable tools are visible.
- [x] Graph state detects relevant file changes across fresh processes; query/update use bounded subprocesses, and graph data survives sessions without committing secrets.
- [x] Context refresh preserves user additions; checkpoints distinguish verified tool outcomes from agent-written notes and never claim gameplay/IDE compliance from file generation.

**Verification:** Fresh-process tests for stale graph/context, missing tools, repeated setup and preserved content; real Graphify command check and disposable-project engine checks.
**Dependencies:** Tasks 1-3, 8. **Files:** `templates/game.py`, `bootstrap.py`, `tests/test_game_cli.py`, `tests/test_bootstrap.py`.

## Task 10: Batch scene capture and review grids

**Description:** Add explicit multi-scene/all-scene capture, bounded concurrency, individual results and labeled comparison grids.

**Acceptance criteria:**
- [x] Repeatable batch selection captures at most three scenes concurrently, keeps deterministic order, continues after per-scene failure, and rejects stale artifacts using a per-call capture ID.
- [x] Individual PNG/manifests remain available; a HTML gallery links full images and PNG contact sheets show up to six scenes each in three columns without cropping screenshots.
- [x] Missing optional Pillow produces an explicit PNG-export limitation and a working HTML gallery; actual export errors/failures cannot masquerade as successful capture.

**Verification:** Fake/real mixed-success batches, duplicate basenames, seven-scene pagination, optional-dependency fallback and visual review of a real six-scene contact sheet.
**Dependencies:** Task 5. **Files:** `templates/game.py`, `templates/core/tools/scene_runner.gd`, new `templates/core/tools/contact_sheet.py`, new `tests/test_contact_sheet.py`, `tests/test_engine_integration.py`.

## Task 11: Reviewed optional grid dependency

**Description:** Let setup propose Pillow for PNG contact sheets without silently installing packages or changing global Python environments.

**Acceptance criteria:**
- [x] A selected PNG-grid option proposes Pillow only when unavailable; installation uses the reviewed project-local environment and exact commands.
- [x] Capture locates the optional project environment for grid export; setup wrapper/docs expose the option and retain the approval gate.

**Verification:** Bootstrap dependency plan/failure tests and contact-sheet exports with the installed Pillow; no network install is claimed without actually exercising it.
**Dependencies:** Tasks 8, 10. **Files:** `bootstrap.py`, `setup.ps1`, `tests/test_bootstrap.py`, `README.md`.

## Completion checkpoint

- [x] Tasks 1-11 satisfy their acceptance criteria and verification (42/42 tests passing in final full run, including capture pruning and clean command).
- [x] Report actual tested engine/platform and remaining limits; no universal compatibility, gameplay or release-ready claim without the corresponding evidence.
- [x] Stop here; MCP and live-editor control stay outside this change.
- [x] Real Antigravity then VS Code agent-session compliance is verified, or explicitly recorded as pending rather than claimed from generated files.

## Evidence and external acceptance

See [VERIFICATION.md](../docs/VERIFICATION.md) for runnable checks and real-engine evidence. Implementation criteria above are separate from real IDE-agent compliance, network dependency installation, additional engines/renderers/platforms and gameplay/device acceptance, which remain pending. Batch PNG grids were visually reviewed from six real 360x640 fixture captures. Real capture tests use explicit 90-second child deadlines on this memory-constrained host; product defaults remain 30 seconds.
