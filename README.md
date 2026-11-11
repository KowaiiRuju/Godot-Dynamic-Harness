# 🎮 Godot Dynamic Harness (GDH)

[![Godot Engine](https://img.shields.io/badge/Godot-4.7%2B-478CBF?logo=godotengine&logoColor=white)](https://godotengine.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Agent Ready](https://img.shields.io/badge/Agents-Antigravity%20%7C%20Claude%20Code%20%7C%20Cursor%20%7C%20Codex-7C3AED)](https://github.com/KowaiiRuju/Godot-Dynamic-Harness)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/KowaiiRuju/Godot-Dynamic-Harness/pulls)

A universal, context-aware AI agent harness, 8-step workflow, and rule framework for **any Godot 4.7+ game project**.

Instead of dumping bloated generic rules or quiz-specific scaffolding into your game, the **Godot Dynamic Harness** instructs coding agents (Google Antigravity, Claude Code, Cursor, Codex, Windsurf) to inspect your project slowly, deduce your game's genre and dimensions (2D/3D RPG, platformer, action, strategy), install and curate the **44 Godot Domain Skills**, enforce **Scene-First UI & Inspector-First `@export` construction**, coordinate multi-agent file leases with **advisory locking**, and deploy a complete **15-subcommand headless test and capture suite** (`game.py`).

---

## 🌟 Why Godot Dynamic Harness?

Most AI coding assistants struggle in Godot projects because they:
1. **Spam dynamic UI code**: They write messy `Control.new()` and `add_theme_*_override()` in GDScript instead of building editable `.tscn` scene trees in the Godot Editor.
2. **Pollute context windows**: They load dozens of irrelevant skills (e.g. loading 3D lighting and multiplayer networking for a 2D single-player pixel RPG).
3. **Lock up the editor**: They run headless tests using the default user directory, freezing or corrupting state when the Godot Editor is already open.
4. **Lack visual proof**: They guess whether menus, HUDs, or inventory windows fit the screen rather than looking at real rendered pixels.
5. **Clobber parallel edits**: Multiple autonomous agents or humans edit the same files simultaneously without concurrency safety or leases.

**Godot Dynamic Harness solves all five out of the box.**

---

## 🧩 The 4 Core Pillars

```
┌──────────────────────────────────────────────────────────────┐
│                  GODOT DYNAMIC HARNESS                       │
├──────────────────────────────┬───────────────────────────────┤
│  1. RECONNAISSANCE           │  2. SKILL CURATION            │
│  - Engine & Viewport config  │  - Graphify (Knowledge Graph) │
│  - 2D vs 3D detection        │  - Ponytail (YAGNI anti-bloat)│
│  - Genre & Systems detection │  - Prompt Master (Meta-AI)    │
│  (RPG, Action, Mobile, etc.) │  - 44 Curated Godot Skills    │
├──────────────────────────────┼───────────────────────────────┤
│  3. SCENE-FIRST & LOCKS      │  4. UNIFIED HARNESS (game.py) │
│  - UI ground truth = .tscn   │  - 15 unified CLI subcommands │
│  - Zero dynamic Control.new()│  - Isolated APPDATA profile   │
│  - Inspector-first @export   │  - Offscreen viewport capture │
│  - Multi-agent file locking  │  - Headless test & QA runner  │
└──────────────────────────────┴───────────────────────────────┘
```

---

## 🔄 The 8-Step Godot Dynamic Harness Workflow

Every agent operation follows this structured lifecycle:

| Step | Phase | Action & CLI Command |
| :---: | :--- | :--- |
| **0** | **Pre-Flight Router & Plan** | `python game.py route-prompt --prompt "<task>" --json` or `python game.py plan-task "<task>" --json` |
| **1** | **Skill Reads & Graph Query** | Read `matched_skill_paths`. Query `graphify query "<feature>"` or inspect with `python game.py scene-outline <scene>`. |
| **2** | **Change Classification & Locks** | Declare **Minor** vs **Major**. When `multi_agent: true`, run `python tools/agent_lock.py acquire <files...>`. |
| **3** | **Scene-First Implementation** | Build visual trees in `.tscn`. Expose tunables with `@export`. Bound GDScript via `%SceneUniqueNames`. |
| **4** | **Proportionate Verification** | Minor: targeted syntax & test suite. Major: full test, capture, and engine validation sweeps. |
| **5** | **Visual Verification** | Render offscreen pixel-perfect snapshots via `python game.py capture --scene <scene>`. |
| **6** | **Write-Off Journaling** | Conclude edits with SHA-256 hashes: `python tools/agent_lock.py write-off <files...> --agent <id>`. |
| **7** | **Context & Graph Refresh** | Run `python game.py context --refresh` and `graphify update .`. |

---

## 🛠️ The 15 Unified `game.py` Subcommands

The harness provides a zero-dependency Python CLI runner at the project root covering the complete development, QA, and maintenance lifecycle:

```bash
# 1. Environment & Project Status
python game.py info

# 2. Prompt & Skill Routing
python game.py route-prompt --prompt "Fix inventory slot dragging" --json

# 3. Structured Task Planning
python game.py plan-task "Add crafting recipe table" --json

# 4. Fast Scene Outline Inspection (No raw .tscn dump)
python game.py scene-outline scenes/ui/hud.tscn

# 5. Offscreen Scene Capture (Isolated QA profile, safe with Editor open)
python game.py capture --scene res://scenes/ui/hud.tscn

# 6. Visual Baseline Regression Testing
python game.py baseline --check

# 7. Headless GDScript Test Runner
python game.py test

# 8. Project Validation & Scene-First Integrity
python game.py validate

# 9. Asset Catalog & Orphan Detection
python game.py assets

# 10. Layout, Bounding Box & Font Audit
python game.py audit

# 11. Persistent Save File Management
python game.py saves

# 12. GDScript Syntax Scan & Version Memory
python game.py syntax --scan .

# 13. Codebase Knowledge Graph Traversal
python game.py graph --query "InventoryManager"

# 14. Persistent Context Summary Generation
python game.py context --refresh

# 15. Temporary File & Cache Cleanup
python game.py clean
```

> **Why the isolated profile matters:**
> `game.py capture` routes offscreen execution through an isolated `APPDATA` directory (`<project>_godot_qa_profile`). You can run test suites and visual captures in your terminal continuously **while Godot Editor stays open**, without engine lockups or crashes.

---

## 🔒 Multi-Agent Concurrency & Advisory File Locking (`tools/agent_lock.py`)

For multi-agent swarms or teams working in parallel:
- **Acquire Lease Before Writing**:
  ```bash
  python tools/agent_lock.py acquire scripts/player.gd scenes/player.tscn --agent worker-1 --task player-move --json
  ```
- **Check Active Leases**:
  ```bash
  python tools/agent_lock.py status --json
  ```
- **Write-Off Changes with SHA-256 Integrity Hashes**:
  ```bash
  python tools/agent_lock.py write-off scripts/player.gd scenes/player.tscn --agent worker-1 --summary "Added jump buffering" --json
  ```

---

## 🚀 Quick Start

### Method 1: The Master Agent Prompt (Recommended)

1. Open your game project in **Google Antigravity**, **Claude Code**, or **Cursor**.
2. Open [`Godot_Dynamic_Harness_Prompt.txt`](Godot_Dynamic_Harness_Prompt.txt).
3. Copy the prompt block and paste it into your agent chat.
4. Watch the agent analyze your game, curate the exact skills needed, install rules and tools, and verify with a headless smoke test!

---

### Method 2: One-Liner PowerShell Bootstrap

Run this command inside your Godot project root folder to install the harness:

```powershell
irm https://raw.githubusercontent.com/KowaiiRuju/Godot-Dynamic-Harness/main/setup.ps1 | iex
```

Or deploy from a local clone:

```powershell
powershell -File C:\Path\To\GDH\setup.ps1 -TargetProject C:\Path\To\MyGame
```

---

## 📜 Scene-First UI Rules (`AGENTS.md`)

The generated `AGENTS.md` strictly binds agents to the **Scene-First** law:
1. **Never write UI in code**: No `Button.new()`, `Label.new()`, or `Control.new()` for layouts.
2. **Never override styles in code**: No `add_theme_stylebox_override()` or dynamic font size hacks in GDScript.
3. **Visually Editable**: All components, cards, dialogues, and screens must exist in `.tscn` files so they can be inspected in the Godot 2D/3D Editor.
4. **Inspector-First `@export`**: Expose gameplay parameters via `@export` instead of private script constants.
5. **ScrollContainer Safety**: Children inside `ScrollContainer` must set `mouse_filter = 1 (Pass)` or `2 (Ignore)` so dragging is never swallowed.

---

## 🤝 Contributing

Contributions, additional domain skills, and game genre templates are welcome! Feel free to open an issue or submit a PR.

## 📄 License

Distributed under the [MIT License](LICENSE).
