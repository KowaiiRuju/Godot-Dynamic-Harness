# Multi-Agent Handoff & Ownership Contract

Use this template when delegating implementation or verification across concurrent workers.

## Handoff Template

```text
Task ID:
Agent ID / Slug & Role: (e.g. 38flsh-med-ui / 3.8-flsh-Med UI Builder)
Goal:
Read-only context paths:
Owned writable paths:
Excluded paths/actions:
Shared-file owner: (Lead owns project.godot, autoloads, game.py)
Verification commands (--json --compact --out):
Owned JSONL log path: .agent-state/logs/<task-id>/<run-id>-<agent-id>.jsonl
Stop conditions:
```

## Worker Rules
- Acquire advisory locks before editing when `>= 2` write workers are active:
  `python game.py lock acquire <files...> --agent <slug> --task <task_id> --json --compact`
- Work strictly within owned writable paths. Report any needed shared-file change to the Lead.
- Conclude edits with proportionate verification and SHA-256 write-off:
  `python game.py lock write-off <files...> --agent <slug> --task <task_id> --summary "..." --json --compact`
- Return compact report: **Changed paths**, **Findings** (`path:line`), **Verification** (command + exit status), **Artifacts**, **Uncertainty/blockers**, **Next action**.
