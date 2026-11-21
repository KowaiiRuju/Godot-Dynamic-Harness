---
name: cavecrew
description: >-
  Route suitable work to bounded agents using Dual-Workhorse orchestration
  (Gemini 4 Hydrogen / Pro lead + Gemini 3.8 Flash workers) and game.py lock
  (agent_lock.py) SHA-256 write-off handoff contracts. See references/multi-agent-handoff.md.
---

# Lead & Dual-Workhorse Workflow (GDH v2)

Follow the repository's [canonical delegation and verification policy](../../../AGENTS.md). This skill defines portable multi-agent handoffs, Dual-Workhorse routing, and `python game.py lock` (`core/tools/agent_lock.py`) concurrency contracts.

## 1. Keep Decisions with the Lead
The Lead agent (Gemini 4 Hydrogen / Pro) owns task interpretation (`python game.py plan-task`), architecture, user art/UI style direction checks, risk, verification scope, shared contracts (`project.godot`, autoloads, `game.py`), integration, and final review. Delegate bounded research or implementation slices with clear acceptance commands. Keep trivial single-file work inline.

## 2. Dual-Workhorse Routing Table

| Role | Assignment | Model & Thinking Recommendation | Required Evidence |
| --- | --- | --- | --- |
| Investigator | Read-only definitions, callers, dependencies, or failure evidence | Gemini 3.8 Flash (High) (`38flsh-high`) | `path:line`, observations, unresolved questions |
| Builder (Routine / UI) | Bounded 1-2 file slice, `.tscn` StyleBox tuning, or visual/doc edit | Gemini 3.8 Flash (Med/High) (`38flsh-med`/`38flsh-high`) | Changed paths, proportionate check output, SHA-256 `write-off` |
| Builder (Deep Logic) | Multi-file refactoring, autoloads, networking, save/migration, FSMs | Gemini 4 Hydrogen / Pro (Med/High) (`4hyd-med`/`4hyd-high`) | Architecture diff, state invariants, suite results, SHA-256 `write-off` |
| Reviewer / Verifier | Read-only verification of diff, `mockup-grade`, and test evidence | Gemini 4 Hydrogen / Pro (High/XHigh) (`4hyd-high`/`4hyd-xtra`) | Findings with `path:line`, severity, test/grade output |

### Tool & Concurrency Configuration
- **`invoke_subagent`**: Use `Model: "flash"` for Discovery Scouts and Routine Builders; `Model: "inherit"` or `"pro"` for Deep Logic Builders and Reviewers. Role format: `<model>-<Think> <Worker>` (e.g., `3.8-flsh-Med UI Builder`, `4-hyd-High Arch Review`).
- **`swarm`**: Worker slug format `<model_slug>-<think>-<role>` (e.g., `38flsh-med-ui`, `4hyd-med-core`).
- **Single-Worker Lock Bypass & Multi-Agent Leases (`python game.py lock`)**:
  - Skip `game.py lock` when working as a single writer (`multi_agent == false`).
  - When `>= 2` concurrent write workers run, each worker MUST acquire leases before editing (`python game.py lock acquire <files...> --agent <slug> --task <task_id> --json --compact`) and conclude with SHA-256 journaling (`python game.py lock write-off <files...> --agent <slug> --task <task_id> --summary "..." --json --compact`).

## 3. Bounded Ownership, Progress & Acceptance
- Use [references/multi-agent-handoff.md](references/multi-agent-handoff.md) and [references/progress-reporting.md](references/progress-reporting.md) when dispatching workers.
- Give each writer a strictly disjoint writable path set; read-only context paths may overlap.
- Return compact, file-first Caveman reports (`Changed paths`, `Findings`, `Verification`, `Artifacts`, `Next action`). Auto-switch to clear prose for safety warnings or irreversible actions.
