---
name: token-budget
description: 3-Tier Context Architecture, hash-gated .context/project_state.json cache, bounded line reads, forbidden directory scans, and zero re-reads after confirmed edits.
---

# Token Budgeting & Context Management (GDH v2)

Context boundary enforcement and token optimization standards for single and multi-agent Godot 4 workflows.

## 1. The 3-Tier Context Architecture

1. **Tier 1: Global Index & Hash-Gated Discovery (Zero File Dumps)**
   - **Zero-Bloat Startup**: Never run `python game.py info --json` on startup. Read `.context/project_state.json` ONLY when a command returns `"ctx_stale": true`.
   - **Outline Before Opening `.tscn`**: Always run `python game.py scene-outline <scene.tscn> --json --compact` to locate node paths, scripts, and signal connections before reading lines.
   - **Major-Only Graphify**: Run `python game.py graph --query "<question>" --json --compact` only on `major` tasks (`skip_graphify == false`).
2. **Tier 2: Scoped Slice & Bounded Reads**
   - Always pass `StartLine` and `EndLine` to `read_file` to inspect only the target function, signal handler, or scene node block.
   - Subagents read only files assigned in their brief or active lease.
3. **Tier 3: Contract Handoff & SHA-256 Journaling**
   - Never paste full scripts, `.tscn` files, or verbose console dumps into chat or swarm board posts.
   - Cite `path:line` ranges and reference `.agent-state/journal.jsonl` SHA-256 entries.

## 2. Anti-Bloat Rules & Landmines
1. **Strictly Forbidden Directory Scans**: Never list, grep, or read across generated/vendor directories: `.godot/`, `.git/`, `.harness/venv/`, `.venv/`, `node_modules/`.
2. **No Re-Reading After Confirmed Edits**: When `edit_file` or `write_file` succeeds, **DO NOT** call `read_file` to re-verify the written text.
3. **UTF-8 Compact CLI Output**: Always pass `--json --compact --out <filepath>` to `python game.py` so outputs use `schema_version: 2` (~180 bytes when `ctx_stale: false`) and write clean UTF-8 LF files without PowerShell `>` UTF-16LE corruption.
4. **Conditional Caveman & ADHD Directness**: Use terse Caveman output for code/QA/handoffs; use normal prose for plans, documentation, dialogue, and lore.
