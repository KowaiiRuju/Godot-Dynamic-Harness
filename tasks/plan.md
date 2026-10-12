# Plan: Dynamic, reliable harness tool calls

Date: 2026-10-13. Status: implementation complete; final verification underway. Execution authorized by the user after the scope interview.
Task checklist: [todo.md](todo.md).

## Goal and scope

Make the existing CLI adapt to the selected Godot project and installed engine. Equip developers and their IDE agents through a review-first setup: inspect the project, write a tailored plan, wait for explicit user approval, then install the selected toolkit and project guidance. Support Antigravity first and VS Code second. Reuse the Python CLI and GDScript runner; no MCP server or live scene controller is needed.

Confirmed scope: reusable inspection/check/test/capture/syntax tools; game-specific helpers and smoke tests proposed only for demonstrated needs; persistent Graphify and project guidance; Graphify before codebase investigations; source/runtime verification afterward. Reduce repeated explanations in fresh sessions with a concise project overview, command reference and verified checkpoint. Preserve existing files, rules and skills. Setup must not install dependencies or execute game code before plan approval.

Additional user request: capture many scenes in one invocation and review them in a labeled grid matching the supplied three-column reference. Preserve individual PNG/manifest evidence, continue past failed scenes, and provide a browsable gallery plus six-scene PNG contact sheets when Pillow is available. Render at most three scenes concurrently; paginate PNG grids to keep memory bounded. Optional PNG-grid dependency installation remains part of the reviewed setup plan.

Success means the same harness can inspect two different projects, use their scene and viewport defaults, select applicable syntax rules for their actual engine, and return results an agent can trust. Unsupported or untested capabilities must be visible. Do not claim universal Godot compatibility from one successful local run.

## Initial evidence (before implementation)

The checkout is a template distribution, not a Godot game: there is no root `project.godot`. No existing test suite or plan was found. There is no existing Graphify graph; findings below come from direct source inspection and focused CLI reproductions.

| Finding | Evidence | Consequence |
| --- | --- | --- |
| Project root is the CLI's directory; `info` reports paths and test count only | `templates/game.py:20`, `:72` | No project settings or engine version are used to adapt calls |
| Engine selection falls back to the first Desktop match, then the string `godot` | `templates/game.py:26` | Invalid explicit settings and missing/ambiguous engines need actionable diagnostics |
| Capture always receives 1280x720 defaults | `templates/game.py:198` | Runner's project viewport fallback is bypassed |
| Capture forces Compatibility on Windows; other systems use headless mode | `templates/game.py:61` | Renderer behavior is assumed by platform, not proved for the project |
| One fixed Windows profile and shared artifact names | `templates/game.py:24`, `scene_runner.gd:52,64` | Projects and concurrent calls can share save state or overwrite evidence |
| Nonexistent scan target succeeds with zero files | Reproduced `python templates/game.py syntax --scan __gdh_missing_scan_target__`, exit 0 | An agent can mistake no work for a passed check |
| Validation prints violations without a failing status | `templates/game.py:120`; reproduced handler returning `None` after a violation | Automation cannot reliably detect a failed audit |
| Child query/learn exit codes are discarded; engine calls have no timeout | `templates/game.py:149,179,184,69` | Errors can look successful; hung calls can block the agent |
| Nested tests are omitted | `templates/game.py:102`; temporary fixture: glob found 0, rglob found 1 | Test counts do not describe all suites |
| Learned rules are not scanned | `docs_updater.py:75,80-97,138`; reproduced learn then scan reporting clean | `Dynamic -> Latest` is excluded, and matchers are hardcoded anyway |
| PNG failure or missing manifest can still end in success | `scene_runner.gd:54-71` | Capture success does not prove the requested artifacts exist |
| Documentation promises more than the CLI provides | README and master prompt versus argparse/handlers | Agents may call nonexistent `--suite` or assume compilation/resource checks occurred |

At planning time, engine discovery was independently probed with `--version`: `4.7.2.stable.official.ed1daf0bf`. That initial probe proved executable discovery only. The later disposable-game, renderer and integration evidence is recorded in [VERIFICATION.md](../docs/VERIFICATION.md).

## Design decisions

1. **Reuse `get_godot_bin`, `run_headless_godot`, `cmd_info`, and the existing documentation loader/saver.** Add small shared helpers only where existing callers need them. Keep command registration in one place; do not build a plugin registry or discover tools by executing arbitrary modules.
2. **Resolve context per invocation.** Proposed precedence: explicit `--project` / `--godot`, existing engine environment variables, then unambiguous discovery. With no project argument, check the deployed CLI directory, then the current directory and its parents. Require `project.godot`; do not recursively select an arbitrary nested project. A supplied invalid engine path must fail, rather than silently selecting another engine.
3. **Use engine and project evidence separately.** Record selected executable, selection source, full `--version`, available flags from `--help`, and authored project feature hints. Project feature tags are compatibility hints, not proof of the currently running engine. Unsupported major versions fail clearly; minor-version support is established by checks and fixtures, not a hardcoded "latest" label.
4. **Read Godot settings with Godot's formats.** Use a small `project_probe.gd` and `ConfigFile` in a disposable scratch project to inspect the target configuration without starting its main scene or autoloads. Return main scene, authored viewport, renderer, features and autoload declarations. Distinguish authored values from runtime-effective settings/overrides, which the capture runner can report through `ProjectSettings`. Do not introduce a general-purpose Python parser for Godot Variant syntax.
5. **Expose the CLI as discoverable agent tools.** Extend `info --json` with context and command capabilities: name, description, arguments/defaults, availability, unavailable reason and mutating flag. Derive command arguments from the same registrations used by argparse. Report `capture` as unverified until the render/artifact check succeeds; an advertised flag is not proof of GPU support. Existing shell calls remain the transport.
6. **One JSON result per call.** Proposed `--json` mode sends exactly one JSON document to stdout; subprocess logs go to stderr or an artifact. Use `schema_version`, `command`, `status`, `context`, `summary`, `findings`, and `artifacts`. Status is `success`, `failed`, `skipped`, or `unsupported`; include stable error codes and file/line locations when known. Exit 0 means successful work or an explicitly reported optional skip; failure, invalid input, timeout, and required unsupported work exit nonzero. Preserve readable default output.
7. **Versioned rules are data, not self-modifying code.** Store applicable target-version bounds, matcher kind/literal, severity, source URL and verification state. Build checks from approved data using escaped literals/token patterns; do not execute learned code or accept arbitrary learned regex. Keep advisory style practices separate from deprecations and engine parse errors. Learned entries without version/source evidence remain queryable notes and are excluded from active checks with an explanation. Validate, deduplicate and atomically replace the JSON file; reject conflicting overwrites. Explicit learning remains a mutating command.
8. **Bound execution and preserve capture fidelity.** All engine and child Python calls need timeouts and error propagation. Each execution gets its own user-data profile and artifact directory. Verify the engine's actual user-data path before promising isolation, including custom user-directory settings. Start capture with the project's renderer; an explicit renderer override must be reported. A renderer fallback must not silently become visual proof for the configured renderer. Missing graphics support is a reported limitation, not a blank-image pass.
9. **No cache in the first implementation.** Resolve fresh facts on each call so switching projects/engines or editing settings/rules cannot leave stale capabilities. Introduce caching only after measured probe cost justifies it and invalidation can be tested.

Proposed flow:

```text
CLI arguments -> resolve project + engine -> check command prerequisites
              -> execute existing handler with bounded subprocesses
              -> verify findings/artifacts -> text or JSON result + exit status
```

Example future calls (not available yet):

```powershell
python game.py --project "C:\Games\MyGame" info --json
python game.py capture --json                       # project main scene + viewport
python game.py capture --scene res://ui/Menu.tscn --width 720 --height 1280 --json
python game.py syntax --scan . --json                # applicable migration hints
python game.py test --suite tests/ui/test_menu.gd --json
```

Example result shape:

```json
{
  "schema_version": 1,
  "command": "capture",
  "status": "failed",
  "context": {"engine_version": "4.7.2", "project_root": "C:/Games/MyGame"},
  "summary": "Screenshot could not be written",
  "findings": [{"code": "ARTIFACT_WRITE_FAILED", "message": "PNG write failed"}],
  "artifacts": []
}
```

## Implementation sequence

1. Make existing failures, skips and timeouts truthful; add the shared result path and focused standard-library tests.
2. Resolve real project/engine context and probe settings without launching game code.
3. Expose capabilities and JSON contracts through `info` and existing commands.
4. Replace fixed syntax matching with applicable, validated rule data.
5. Adapt capture defaults, rendering and artifact/profile handling to the selected project.
6. Make test discovery recursive/selectable and prove engine checks separately from migration scans.
7. Align README, the master prompt and generated agent instructions with verified behavior.
8. Implement a review-first bootstrap that records exact file changes/dependency actions, detects stale plans/conflicts and applies only an explicitly approved plan.
9. Persist project context, tool commands, Graphify freshness and session checkpoints with concise Antigravity/VS Code instruction adapters.
10. Capture selected/all scenes with bounded concurrency and labeled HTML/PNG review grids, keeping individual evidence and per-scene failures.
11. Offer optional Pillow installation through the reviewed project-local dependency plan.

Each item has acceptance criteria, dependencies and file scope in [todo.md](todo.md). Checkpoints follow tasks 1-3, 4-6 and 7. The first implementation slice is task 1; do not rewrite the whole harness at once.

## Verification and completion bar

- Standard-library `unittest` fixtures cover missing/invalid/ambiguous engines, missing projects, project paths with spaces, alternate viewport/main-scene settings, invalid scene/dimensions, missing scan paths, nested suites, child failures, timeouts and JSON stdout purity.
- Version fixtures cover old supported, current and unknown/new engine responses, plus a different major version. Mocked versions prove selection logic only; label which real binaries were exercised.
- Learn/query/scan tests prove that an approved applicable learned rule becomes a finding, out-of-range/unverified entries do not become active rules, and malformed or conflicting updates leave the old JSON intact.
- Disposable Godot fixtures cover valid and invalid scripts, broken scene resources, script/assertion errors that must not be hidden by process exit status, and no-test skips. Use engine parse/load checks separately from the advisory migration scanner; neither regex scans nor editor startup alone prove complete compilation or gameplay correctness.
- A real local capture must return a readable nonempty PNG at the requested/project dimensions, a valid matching manifest, the actual renderer/settings, and distinct paths for repeated/concurrent calls. Force PNG/manifest write failures and confirm nonzero status. Verify isolated save paths with two projects.
- Re-run context discovery after changing project settings, engine selection and rule data. Results must change without manual cache deletion.
- Keep static checks, engine checks, capture proof and gameplay/device acceptance distinct. Cross-platform rendering and other engine versions remain unverified until exercised on those environments.

## Risks and limits

| Risk | Mitigation |
| --- | --- |
| Project overrides/UID scene paths differ from authored config | Report authored versus effective values; resolve scene UIDs with the selected engine |
| Starting a project can execute autoloads, tools, plugins or filesystem/network code | Keep discovery in a scratch probe project; run execution tests only on disposable fixtures |
| Headless execution has no usable render target | Probe actual capture artifacts; require graphics-capable execution for visual proof |
| Text migration matching can misread strings/comments or miss semantics | Test lexical edge cases, call findings advisory, use engine checks for syntax validity |
| A template update overwrites a project's customized harness/rules | No installer overwrite or destructive skill pruning in this plan; document manual adoption |
| Unverified database entries become authoritative | Require source/version provenance; remove or mark vague claims such as the existing PackedDataContainer entry unverified |

## Deferred deliberately

MCP transport, a running-editor bridge, automatic engine installation, online self-updating rules, full genre classification, skill deletion, screenshot baseline comparisons and device/release certification. Dependency installation is limited to reviewed actions; no bulk skill-library installation or pruning. Comprehensive gameplay test generation is outside scope; a reusable smoke test may be selected in the reviewed plan.

## Execution notes

The engine checker parses/loads selected resources with existing import metadata. Automatic editor import was excluded after standalone `--import`, editor/quit and graphics-backed import attempts hung on this Windows Godot 4.7.2 host. Open asset-heavy projects in the editor before checking them; do not present this limitation as a passed import gate.

Batch capture follows the supplied three-column reference: up to six labeled scenes per PNG page, a clickable HTML gallery, three concurrent isolated renders, and retained per-scene PNG/manifests. A per-call ID rejects stale artifacts. PNG sheets use optional Pillow; missing Pillow leaves a working HTML gallery and an explicit limitation.

See [verification evidence](../docs/VERIFICATION.md) for actual checks and pending external acceptance. Generated IDE instructions do not prove agent-session compliance or token savings.

## Official references checked

- [Godot command-line tutorial](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html): explicit `--path`, `--version`/`--help`, script execution, headless mode and `--check-only` with `--script`.
- [ProjectSettings](https://docs.godotengine.org/en/stable/classes/class_projectsettings.html): project configuration and effective setting overrides.

These web references describe the retrieved documentation, not a promise that every installed engine supports every flag. Probe the selected binary and use matching version documentation during implementation.
