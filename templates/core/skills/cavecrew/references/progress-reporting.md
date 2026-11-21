# Live Progress Contract for Lead and Workers

## Worker Event Logging
When assigned an exclusive `.agent-state/logs/<task-id>/<run-id>-<agent-id>.jsonl` log path, append one UTF-8 JSON object per line at phase boundaries:

```json
{"time_utc":"2026-10-28T02:10:00Z","task_id":"hud-layout","agent_id":"38flsh-med-ui","status":"running","phase":"mockup-grade","done":"Updated StyleBoxTexture margins in hud.tscn","current":"Running game.py mockup-grade","next":"Write-off lease and report","evidence":["scenes/ui/hud.tscn:24"]}
```

- Valid `status` values: `started`, `running`, `waiting`, `blocked`, `failed`, `completed`, `stopped`.
- Report immediately on any `LOCK_CONFLICT`, `VSCODE_USER_PRIORITY`, or verification failure.
