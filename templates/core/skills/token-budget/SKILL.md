---
name: token-budget
description: Context boundary enforcement, 3-tier context architecture, and token optimization for multi-agent workflows.
---

# Token Budgeting & Context Management

Token budgeting and context optimization standards for single and multi-agent workflows in Godot 4 development. Prevents context window exhaustion, reduces latency, eliminates hallucination risks from noisy context, and enforces lean agent communication.

## 1. The 3-Tier Context Architecture

Agent context is managed through a tiered model that escalates detail only when required:

```text
+-------------------------------------------------------------------+
| Tier 1: Global Index & Discovery                                  |
| (graphify queries, scene-outline, game.py info, knowledge graph)   |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
| Tier 2: Scoped Slice & Bounded Reads                              |
| (Targeted files in lease, StartLine/EndLine bounded reads)        |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
| Tier 3: Contract Handoff & Journaling                             |
| (path:line references, SHA-256 journal entries, concise JSON)     |
+-------------------------------------------------------------------+
```

### Tier 1: Global Index & Discovery (Zero File Dumps)
- **Never scan directories blindly**: Do not run recursive file listings or broad grep searches when looking for symbols, scenes, or dependencies.
- **Use Graphify First**:
  - Run `graphify query "<question>"` or `python game.py graph --query "<question>" --json` to locate relevant files, nodes, and relationships.
  - Run `graphify path "<source>" "<target>"` to understand call graphs.
- **Inspect Scene Outlines Before Opening `.tscn` Files**:
  - Godot `.tscn` scenes often contain hundreds of lines of connection tables, sub-resources, and transform data.
  - Run `python game.py scene-outline <scene.tscn> --json` to see the node hierarchy and script attachments before reading lines.
- **Project High-Level Status**:
  - Run `python game.py info --json` for engine version, renderer, and active configuration.

### Tier 2: Scoped Slice & Bounded Reads
- **Only Read Leased / Assigned Files**: Subagents must restrict reads strictly to files named in their brief or acquired under their active lease.
- **Bounded Line Reads**:
  - Always use `StartLine` and `EndLine` in `read_file` to view the specific function, signal connection, or node definition under investigation.
  - Never read an entire 800-line script to inspect a 20-line helper method.
- **Diff-Oriented Inspection**:
  - Focus reading on recent Git diffs or git blame rather than whole-file scans.

### Tier 3: Contract Handoff & Journaling
- **No Code Dumps in Chat**:
  - Never paste entire scripts, `.tscn` text, or large log blocks into agent messages or turn responses.
  - Use file path citations with line numbers: `[hud.gd](file:///c:/Users/Acer/Documents/redone-network-check/scripts/ui/hud.gd#L45-L62)`.
- **Journal as State Source of Truth**:
  - Refer to `.agent-state/journal.jsonl` for verified file hashes and changes rather than re-transmitting file contents.
- **Structured JSON Handoffs**:
  - Subagents communicate findings and verification to the lead using structured JSON or the standard compact cavecrew handoff format (`Changed paths`, `Findings`, `Verification`, `Artifacts`, `Next action`).

---

## 2. Anti-Bloat Rules & Landmines

### 1. Strictly Forbidden Directory Scans
Never execute directory listings, search commands, or file reads across generated or massive folders:
- `.godot/` (engine shader cache, UID tables, imported textures)
- `.venv/` / `env/` (Python virtual environments)
- `ref/` / `references/` (large design asset dumps)
- `.git/` (raw Git object trees)
- `node_modules/` (if web/JS tooling is present)

### 2. No Re-Reading After Confirmed Edits
- When `edit_file` or `write_file` completes successfully, **DO NOT** call `read_file` to re-read the file just to verify it was written.
- The tool result already reports success and displays the applied chunk. Re-reading burns tokens redundantly.

### 3. Bounded CLI Tool Output
- Always pass `--json`, `--summary`, or `--quiet` flags to CLI tools (`game.py`, `tools/capture.py`, `pytest`) to avoid multi-thousand line console dumps.
- When inspecting failures, pipe through `Select-Object -First 20` or similar shell filters rather than capturing unlimited terminal output.

### 4. Caveman Mode & ADHD Conciseness
- Use Caveman mode (lite/full) for technical handoffs, bug reports, and progress updates.
- Strip conversational filler, boilerplate greetings ("Hi!", "Sure, I can help with that"), and redundant summaries.
- Keep output dense, factual, and actionable.

---

## 3. Subagent Prompt Sizing Guidelines

When a Lead agent invokes or messages a subagent:
1. **Target Prompt Budget**: Keep subagent prompts under 1,500 tokens.
2. **Context by Reference, Not Value**:
   - Provide file paths and line ranges (`scripts/world/crops.gd:40-80`) rather than inlining source code into the prompt.
3. **Explicit Boundary Fields**:
   - State exact owned writable paths, read-only context paths, and excluded paths.
4. **Concrete Stopping Point**:
   - Clearly state the single acceptance test command and evidence required so the subagent stops promptly upon completion without wandering.
