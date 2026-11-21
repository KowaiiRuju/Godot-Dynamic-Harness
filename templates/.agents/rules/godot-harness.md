---
trigger: always_on
description: Godot Dynamic Harness tools, Graphify navigation, Scene-First authoring and persistent context.
---

<!-- GODOT-HARNESS:BEGIN -->
# Godot Dynamic Harness Workflow
1. Delegation Fast-Start & Turn-1 Prompt JSON Dissection: Lead dissects the user prompt into structured JSON (`intent`, `task_category`, `art_domain`, `multi_agent`, `keywords`, `target_files`, `graph_queries`) and dispatches a Flash subagent via `invoke_subagent(Model="flash", TypeName="self")` on Turn 1 (using read-only constraints for discovery so the worker has shell access to run `python game.py route-prompt`, or `TypeName="research"` only after `route-prompt` is already executed). Lead never runs raw source reads or broad greps inline.
2. Worker Python Router Execution & Receipt: Flash subagents run Step 0 `python game.py route-prompt --payload-file <path> --json` (or `--payload-b64 <b64>` / `--payload '<PromptJSON>'` / `python game.py plan-task "<prompt>" --json`), call `read_file` on all returned `matched_skill_paths`, execute graph queries, log audit records to `.agent-state/logs/router_audit.jsonl`, and return concise `path:line` citations, `audit_id`, and `Skills applied: [...]` receipt to Lead for main-chat display.
3. Lead Acceptance & Coordination: Lead reviews the compact subagent handoff, approves the change class (`Minor` vs `Major`), plans slices, and acquires locks via `tools/agent_lock.py` when `multi_agent: true`.
4. Conditional Caveman: Resolved automatically by Layer 2 of `tools/skill_router.py`. Use Caveman mode (`caveman_full` + `caveman`/`cavecrew`/`ponytail`) for `coding`, `bugfix`, `tuning`, `qa`, and `refactor`. Switch to normal prose for `planning`, `docs_or_lore`, and walkthroughs.
5. Autonomous Safe Execution: Once a plan is approved, execute all phases autonomously end-to-end. Do not prompt for repeated intermediate approvals.
6. Proportionate Verification: Minor changes run targeted syntax/suite/baseline checks. Major changes run full test/capture/validation sweeps.
7. Scene-First & Inspector-First: Build UI and actor node structures in `.tscn` hierarchy (no procedural UI via `.new()`). Expose tunable gameplay numbers with `@export`. Align 2D top-down origins to ground contact and enable `y_sort_enabled`.
8. Single Runner Reuse: Keep graph and context current. Use `game.py` unified CLI tools (`game.py info`, `game.py route-prompt`, `game.py plan-task`, `game.py scene-outline`, `game.py graph`, `game.py test`, `game.py capture`, `game.py context --refresh`) instead of creating ad-hoc runners.
<!-- GODOT-HARNESS:END -->
