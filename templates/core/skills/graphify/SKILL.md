---
name: graphify
description: "Godot knowledge-graph navigation and dependency queries at graphify-out/ using python game.py graph --refresh / --query and graphify query / path / explain under the Major-Changes-Only policy."
---

# /graphify — Godot Knowledge Graph Navigation (GDH v2)

## 1. Major-Changes-Only Policy (`skip_graphify`)
- **Querying Graphify**: Automatic or pre-flight Graphify queries run **ONLY for `Major` changes** (`triage_category == "major"`, `skip_graphify == false`, cross-system/`>2` core files, architecture/autoload/save/multiplayer overhauls).
- **Skip on Minor Tasks**: Skip Graphify completely on `trivial_chat`, `quick_question`, `minor_doc`, `minor_visual`, `minor_logic`, and single-scene `ui_mockup` tasks.
- **Rebuilding Graphify**: Refresh the graph (`python game.py graph --refresh --timeout 120 --json --compact` or `graphify update .`) **ONLY after `Major` code/scene changes** or when `graph_state` is `missing`/`stale` during a major investigation.

## 2. Primary Godot Harness Commands (`python game.py graph`)
The harness indexes Godot `.gd` classes, functions, signals, `.tscn` node hierarchies, and explicit `res://` resource links alongside Python/C# AST nodes into `graphify-out/graph.json`:

```powershell
# 1. Check graph freshness and node/edge counts
python game.py graph --json --compact

# 2. Refresh/build the persistent Godot + Graphify source graph (Major changes only)
python game.py graph --refresh --timeout 120 --json --compact --out .agent-state/graph_refresh.json

# 3. Query scoped dependencies with a token budget cap
python game.py graph --query "<symbol, scene, or architectural question>" --budget 800 --json --compact --out .agent-state/graph_query.json
```

## 3. Direct Graphify CLI Subcommands (When `graphify-out/graph.json` Exists)
When querying specific relationships across a fresh `graphify-out/graph.json`:
- **Broad BFS/DFS Concept Query**:
  `graphify query "<question>" --budget 1500` (add `--dfs` to trace a specific call/reference chain)
- **Shortest Path Between Two Nodes**:
  `graphify path "<SourceNode>" "<TargetNode>"`
- **Focused Node Explanation**:
  `graphify explain "<NodeOrAutoloadName>"`

## 4. Verification & Delegation Rules
- **Source Remains Evidence**: Graph results are navigation hints. Always verify matched `source_location` lines against the actual `.gd` or `.tscn` file (using `python game.py scene-outline <scene.tscn> --json --compact` before bounded `read_file` calls).
- **No Concurrent Rebuilds**: In multi-agent swarms, only the Lead agent runs `python game.py graph --refresh`. Workers query the existing `graphify-out/graph.json` read-only.
- **Backup Preservation**: Existing untracked or user-modified `graphify-out/graph.json` files are automatically backed up to `.harness/graph-backups/` before adoption.
