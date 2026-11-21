---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ ONLY for major architectural changes (skip_graphify: true on minor tasks).
---

# Graphify Knowledge Graph Policy (GDH v2)

This project maintains a persistent Godot + Graphify knowledge graph at `graphify-out/graph.json`.

**Mandatory Policy: Run Graphify ONLY for Major changes (`skip_graphify == false`).**

## Rules
1. **Querying Graphify (`Major` Changes Only)**:
   - Run `python game.py graph --query "<question>" --json --compact` (or `graphify query "<question>"`, `graphify path "<A>" "<B>"`, `graphify explain "<concept>"`) **ONLY for `Major` tasks** (`triage_category == "major"`, cross-system/`>2` core files, architecture/autoload/save/multiplayer overhauls).
   - **Skip Graphify completely** on `trivial_chat`, `quick_question`, `minor_doc`, `minor_visual`, `minor_logic`, and single-scene `ui_mockup` tasks (`skip_graphify: true`).
2. **Navigating Existing Graph Outputs**:
   - When `graphify-out/wiki/index.md` exists during a major architectural review, navigate it before reading raw files.
   - Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review when scoped queries do not surface enough context.
   - Always verify graph `source_location` hints against the actual `.gd` or `.tscn` source files.
3. **Rebuilding Graphify (`Major` Changes Only)**:
   - Run `python game.py graph --refresh --timeout 120 --json --compact` (or `graphify update .`) **ONLY after `Major` code/scene changes** in a session — never rebuild Graphify after minor or documentation edits.
