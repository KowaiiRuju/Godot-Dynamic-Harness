# Verification evidence

Date: 2026-10-13. Local environment: Windows, Python 3.12, Godot `4.7.2.stable.official.ed1daf0bf`, installed Graphify and Pillow. All engine execution uses disposable projects, not the user's game. Changes are uncommitted.

## Implemented and exercised

| Area | Evidence |
| --- | --- |
| Tool results | JSON stdout, argument/launch errors, nonzero child exits, script errors despite exit 0, explicit skips and owned-process-tree timeout cleanup |
| Project context | Real scratch configuration probes; actual engine version/help, changed viewport settings, paths with spaces, no target autoload execution during discovery |
| Version rules | Approved learning affects scans within numeric bounds; strings/comments and token boundaries handled; invalid/conflicting inputs preserve prior data |
| Engine checks/tests | Real parse/load checks, broken scene references, recursive/selected suites, assertions and timeout failures |
| Capture | Real default 640x360 and overridden 720x1280 PNG/manifests; actual Compatibility renderer; concurrent isolated save/artifact paths; forced file-write failures |
| Batch capture | Six successful scenes plus a missing seventh; deterministic order, duplicate basenames, retained individual artifacts, two PNG pages; stale artifacts rejected when a scene exits before capture |
| Grid export | Seven-record pagination, failure tiles, HTML escaping/relative links, aspect-preserving PNGs, missing-Pillow HTML fallback; grid timeout retains individual evidence |
| Review-first setup | No-install planning, exact review diffs/digest, altered/stale plan rejection, both IDE adapters, preserved notes, custom-file conflicts, dependency failure, partial-write rollback and idempotent apply |
| Persistence | Real reviewed setup with Graphify and selected smoke test; fresh-process queries and context; source changes mark graph/context stale; modified/untracked graphs backed up |
| Optional dependencies | Reviewed project-local Graphify/Pillow commands; installed Pillow used for actual exports; no network package installation performed |
| Capture retention & cleanup | Automatic pruning of debug captures (5 newest retained); explicit clean --captures and --all; .gitignore rules for binary screenshots and review grids |

A separate `capture --all-scenes` run captured six portrait fixture scenes at 360x640. The resulting 992x1218 contact sheet was visually inspected: three columns, two rows, readable path labels and uncropped screenshots. Local ignored evidence: `qa-evidence/batch-grid/contact_sheet_001.png` and `gallery.html`. These fixture images prove capture/export behavior, not the appearance or gameplay of a user's game.

## Reproduce

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

The suite uses Python's standard-library unittest. Engine tests explicitly skip when Godot is unavailable; the real Graphify integration skips when Graphify is unavailable. A passing run with skips is not proof of those skipped integrations.

On an installed game, compare a relevant set or all discovered scenes:

```powershell
python game.py capture --scenes res://Menu.tscn res://Levels/Level01.tscn --json
python game.py capture --all-scenes --json
```

Inspect result status/findings, gallery/contact sheets and full-resolution PNG/manifests. A failed scene or exporter makes the batch fail while preserving completed individual evidence. Use runnable scenes; components that need parents/game state require explicit setup.

## Limits and pending acceptance

- Automatic editor import hangs on this host. The checker uses existing import metadata and does not claim a successful import/complete compilation gate. Open asset-heavy projects in Godot before checking.
- Capture uses a graphics-capable engine process. Dummy `--headless` rendering cannot provide visual proof; rendering windows may appear. Only the local Compatibility renderer was exercised.
- Earlier integration runs exposed a Windows checkpoint containment failure and an outer-test timeout. Equivalent resolved extended-path prefixes are now normalized, with an outside-path regression check. The concurrent test now covers the wrapper's multiple bounded phases and cleans up its owned process tree. Scratch configuration probes also hit 30-second deadlines under host load: only about 365 MB of 8 GB RAM was free, with another project's Godot tests running. Those unrelated processes were left alone. Real capture fixtures now use explicit 90-second child budgets; product defaults remain 30 seconds and intentional timeout tests still use their shorter deadlines. One earlier Graphify query failed and its isolated rerun passed; failures remain visible rather than being silently retried. Resource pressure is an inference, not a confirmed engine diagnosis.
- Real Antigravity, then VS Code, agent-session compliance and actual token savings remain unverified. Native rule files and persistent context were tested; agents can still bypass instructions.
- HTML markup, links and fallback were tested; live desktop/mobile browser layout is pending because no browser was connected. PNG sheets were visually inspected.
- Linux execution, additional real Godot versions, other renderers, network dependency installs, gameplay, device and release acceptance remain unverified. Mocked engine versions prove branching only. Execution on macOS/other platforms is explicitly unavailable until save-profile isolation is implemented.
- The source graph covers Godot declarations, scene nodes and explicit resource paths, plus Python/C# AST. Dynamic paths, signal wiring, UID relationships, shaders and runtime behavior require direct inspection.
- Save-profile isolation does not sandbox project code. Execution can run autoloads/project code; source/resource checks and screenshots are separate evidence from gameplay correctness.
