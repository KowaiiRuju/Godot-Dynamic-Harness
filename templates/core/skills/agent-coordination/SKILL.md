---
name: agent-coordination
description: Advisory file locking, multi-agent lease handoffs, unified write-off journaling, and VS Code + Antigravity concurrency safety.
---

# Agent Coordination & Concurrency Control

Advisory file locking, multi-agent lease handoffs, unified write-off journaling, and VS Code + Antigravity concurrency safety. Ensures multiple autonomous agents and human developers can work in the same repository simultaneously without clobbering edits or causing merge conflicts.

## 1. Core Principles

1. **Explicit Lease Ownership**: An agent must hold an active lease on a file before writing to it.
2. **Non-Overlapping Writable Paths**: Multi-agent squads must operate on strictly disjoint writable path sets.
3. **Collision Avoidance**: If a lock collision occurs, the agent immediately yields the conflicting slice and reports the block to the lead.
4. **Mandatory Write-Off**: Edits are concluded by writing SHA-256 hashes to the unified journal and releasing the lock.
5. **Human & IDE Priority**: Leases claimed by human developers or VS Code (`--agent vscode-user`) take immediate priority.

---

## 2. Pre-Flight Check & Lease Acquisition

Before modifying any file (scenes, scripts, resources, or configurations), an agent **MUST** run the lock acquisition CLI:

```bash
python tools/agent_lock.py acquire <files...> --agent <agent_id> --task <task_id> --json
```

### Checking Active Leases
To inspect current locks across all agents and sessions:
```bash
python tools/agent_lock.py status --json
```

### Lease Mechanics
- Leases are stored in `.agent-state/leases.json`.
- Each lease records:
  - `path`: Target file path (normalized relative to repository root).
  - `agent_id`: Identifier of the claiming agent (e.g. `worker-builder-1`, `vscode-user`).
  - `task_id`: Identifier of the task slice.
  - `acquired_at`: ISO 8601 UTC timestamp.
  - `expires_at`: Expiration timestamp based on TTL (default 1800s / 30m).

---

## 3. Collision Resolution & Protocol

When `tools/agent_lock.py acquire` returns exit code 1, a lock conflict has occurred:

```text
[ERROR] File locked by 'worker-builder-2' (Task: inventory-refactor, Expires: 2026-11-07T07:15:00Z)
```

### Collision Rules:
1. **NEVER Force or Bypass**: Never attempt to overwrite a locked file. Never edit or delete `.agent-state/leases.json` directly to bypass a lock.
2. **Halt the Affected Slice**: Immediately stop work on the contested file.
3. **Log the Conflict**: Record a `blocked` status event in the agent's task log (`.agent-state/logs/<task-id>/<run-id>-<agent-id>.jsonl`):
   ```json
   {"timestamp": "...", "task_id": "...", "agent_id": "...", "status": "blocked", "conflict_path": "path/to/file", "held_by": "worker-builder-2"}
   ```
4. **Work on Orthogonal Files or Report**:
   - If the assigned task brief includes other unlocked files, proceed with those.
   - Otherwise, immediately send a message to the lead agent reporting the collision and file path.
5. **Lock Expiration & Stale Recovery**:
   - Only the Lead agent is authorized to force-release an expired or orphaned lease:
     ```bash
     python tools/agent_lock.py release <files...> --force --agent <lead_id> --json
     ```

---

## 4. Exclusive Ownership & Squad Matrix

Before dispatching multi-agent tasks, the Lead agent must define a non-overlapping **Agent Squad & Ownership Matrix** in the implementation plan:

| Agent Role | Subagent ID | Owned Writable Paths | Read-Only Context Paths | Progress Log Path |
| --- | --- | --- | --- | --- |
| Worker-Builder-1 | `worker-slice1` | `scripts/ui/hud.gd`, `scenes/ui/hud.tscn` | `scripts/autoload/game_state.gd` | `.agent-state/logs/<task>/run1-worker1.jsonl` |
| Worker-Builder-2 | `worker-slice2` | `scripts/world/crops.gd`, `scenes/world/crop.tscn` | `scripts/autoload/game_state.gd` | `.agent-state/logs/<task>/run1-worker2.jsonl` |
| Lead Integrator | `lead-argon` | `project.godot`, `game.py`, shared autoloads | All repository files | `.agent-state/logs/<task>/run1-lead.jsonl` |

### Rules for Shared Files:
- Shared entry points (e.g., `project.godot`, autoload singletons, `game.py`, common base classes) must be owned exclusively by the **Lead Integrator**.
- Workers that require changes to shared files must propose the exact diff or interface change in their handoff report to the Lead.

---

## 5. Mandatory Write-Off & Journaling

Completing an edit requires a formal write-off. Once files have been modified and verified:

```bash
python tools/agent_lock.py write-off <files...> --agent <agent_id> --summary "<concise summary>" --json
```

### What Write-Off Does:
1. Calculates SHA-256 checksums of the written files.
2. Appends an immutable audit entry to `.agent-state/journal.jsonl`:
   ```json
   {
     "timestamp": "2026-11-07T06:15:30Z",
     "agent_id": "worker-slice1",
     "task_id": "hud-clock-sync",
     "path": "scripts/ui/hud.gd",
     "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "summary": "Bound clock label to GameState day_tick signal"
   }
   ```
3. Releases the active lease from `.agent-state/leases.json`.

> **IMPORTANT**: Never report a task slice as complete without executing `write-off`. An un-journaled change is considered unverified and uncommitted.

---

## 6. Co-Working with VS Code / Human User

Human developers and VS Code Copilot sessions can claim locks to prevent autonomous background agents from touching active workspaces:

### Claiming Manual Leases:
```bash
python tools/agent_lock.py acquire <files...> --agent vscode-user --task manual-edit --ttl 7200 --json
```

### Automated Batch Pre-Check:
Autonomous agents and background runners must run `status` before executing sweeping operations (such as refactoring, formatting, or asset importing):
```bash
python tools/agent_lock.py status --json
```
If any file in the operation is locked by `vscode-user`, the agent must omit that file or postpone the operation.

---

## 7. Subagent Execution Checklist

When operating as a delegated subagent:
- [ ] 1. **Check Brief**: Verify assigned task ID, owned writable paths, and log path.
- [ ] 2. **Log Started**: Append `{"status": "started", ...}` to assigned `.agent-state/logs/...` file.
- [ ] 3. **Acquire Locks**: Run `tools/agent_lock.py acquire <files...>` on all writable targets.
- [ ] 4. **Execute Edits**: Make minimal, scene-first, inspector-accessible modifications.
- [ ] 5. **Run Verification**: Execute the proportionate checks specified in the brief.
- [ ] 6. **Write-Off**: Run `tools/agent_lock.py write-off <files...> --summary "..."`.
- [ ] 7. **Log Completion**: Append `{"status": "completed", ...}` to task log.
- [ ] 8. **Handoff Report**: Send structured completion message to the Lead with paths, findings, verification, and artifacts.
