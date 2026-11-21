---
name: agent-coordination
description: Advisory file locking, single-worker bypass, multi-agent lease handoffs, SHA-256 write-off journaling, and human IDE priority via python game.py lock (core/tools/agent_lock.py). Load when running multi-agent swarms or coordinating file ownership.
---

# Agent Coordination & Concurrency Control (GDH v2)

Advisory file locking, multi-agent lease handoffs, unified SHA-256 write-off journaling, and VS Code / Antigravity concurrency safety via `python game.py lock` (`core/tools/agent_lock.py`).

## 1. Core Principles & Single-Worker Lock Bypass
1. **Single-Worker Lock Bypass**: Skip `python game.py lock acquire` when operating as a single agent (`multi_agent == false`). Acquire leases only when `>= 2` concurrent write workers run in `swarm` or co-working with a human `vscode-user` lease.
2. **Explicit Lease Ownership**: In multi-agent mode, a worker must hold an active lease on every target file before modifying it.
3. **Disjoint Writable Paths**: Multi-agent squads operate on non-overlapping writable path sets; shared files (`project.godot`, autoloads, `game.py`) remain with the Lead Integrator.
4. **Mandatory SHA-256 Write-Off**: Conclude multi-agent edits with `write-off`, recording SHA-256 file hashes in `.agent-state/journal.jsonl` and releasing the lease.
5. **Human & IDE Priority**: Leases claimed by `--agent vscode-user` take immediate priority over autonomous workers.

## 2. Lease Acquisition, Status & Pre-Flight Checks
- **Acquire Leases Before Editing**:
  ```powershell
  python game.py lock acquire <files...> --agent <agent_id> --task <task_id> --json --compact
  ```
  (Or directly: `python core/tools/agent_lock.py acquire <files...> --agent <agent_id> --task <task_id> --json`)
- **Check Active Leases**:
  ```powershell
  python game.py lock status --json --compact
  ```
- **Check Specific Files**:
  ```powershell
  python game.py lock check <files...> --json --compact
  ```
- **Agent Slug Format**: `<model_slug>-<think>-<role>` (e.g., `38flsh-med-ui`, `4hyd-med-core`, `4hyd-xtra-lead`, or `vscode-user`).

## 3. Collision Resolution Protocol
When `lock acquire` exits nonzero (`LOCK_CONFLICT` / `VSCODE_USER_PRIORITY`):
1. **Never Force or Bypass**: Never overwrite a locked file or edit `.agent-state/leases.json` manually.
2. **Halt the Contested Slice**: Proceed only with orthogonal unlocked files in your brief, or report the blocker (`conflict_path`, `held_by`) to the Lead agent.
3. **Stale Recovery**: Expired leases are pruned automatically or via `python game.py lock prune --json --compact`. Only the Lead may run `python game.py lock release <files...> --force --agent <lead_id> --json --compact`.

## 4. Mandatory Write-Off & SHA-256 Journaling
Once multi-agent edits and proportionate verification finish, run:
```powershell
python game.py lock write-off <files...> --agent <agent_id> --task <task_id> --summary "<concise summary>" --json --compact
```
This computes SHA-256 digests of modified files, appends an audit record to `.agent-state/journal.jsonl`, and releases the active leases in `.agent-state/leases.json`.
