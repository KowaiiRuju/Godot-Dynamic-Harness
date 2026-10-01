# 🎮 Godot Dynamic Harness

[![Godot Engine](https://img.shields.io/badge/Godot-4.7%2B-478CBF?logo=godotengine&logoColor=white)](https://godotengine.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AI Agent Ready](https://img.shields.io/badge/Agents-Antigravity%20%7C%20Claude%20Code%20%7C%20Cursor-7C3AED)](https://github.com/KowaiiRuju/Godot-Dynamic-Harness)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/KowaiiRuju/Godot-Dynamic-Harness/pulls)

A universal, context-aware AI agent setup harness and rule framework for **any Godot 4.7+ game project**. 

Instead of dumping bloated generic rules or quiz-specific scaffolding into your game, the **Godot Dynamic Harness** instructs coding agents (Google Antigravity, Claude Code, Cursor, Codex) to read your project slowly, deduce your game's genre and dimensions (2D/3D RPG, platformer, action, strategy), install and curate the **44 Godot Domain Skills**, enforce **Scene-First UI construction**, and deploy an offscreen **headless scene capture & test suite**.

---

## 🌟 Why Godot Dynamic Harness?

Most AI coding assistants fail in Godot projects because they:
1. **Spam dynamic UI code**: They write messy `Control.new()` and `add_theme_*_override()` in GDScript instead of building editable `.tscn` scene trees in the Godot Editor.
2. **Pollute context windows**: They load dozens of irrelevant skills (e.g. loading 3D lighting and multiplayer networking for a 2D single-player pixel RPG).
3. **Lock up the editor**: They run headless tests using the default user directory, freezing or corrupting state when the Godot Editor is already open.
4. **Lack visual proof**: They guess whether menus, HUDs, or inventory windows fit the screen rather than looking at real rendered pixels.

**Godot Dynamic Harness solves all four out of the box.**

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
│  3. SCENE-FIRST RULES        │  4. HEADLESS HARNESS          │
│  - UI ground truth = .tscn   │  - Offscreen viewport capture │
│  - Zero dynamic Control.new()│  - Isolated APPDATA profile   │
│  - Layer Cake architecture   │  - Node rect & font manifest  │
│  - "Signal Up, Call Down"    │  - python game.py CLI runner  │
└──────────────────────────────┴───────────────────────────────┘
```

---

## 🚀 Quick Start

### Method 1: The Master Agent Prompt (Recommended)

1. Open your game project in **Google Antigravity**, **Claude Code**, or **Cursor**.
2. Open [`Godot_Dynamic_Harness_Prompt.txt`](Godot_Dynamic_Harness_Prompt.txt).
3. Copy the prompt block and paste it into your agent chat.
4. Watch the agent analyze your game, curate the exact skills needed, write `AGENTS.md`, and verify with a headless smoke test!

---

### Method 2: One-Liner PowerShell Bootstrap

Run this command inside your Godot project's root folder to pull the core meta-tools and skill libraries:

```powershell
irm https://raw.githubusercontent.com/KowaiiRuju/Godot-Dynamic-Harness/main/setup.ps1 | iex
```

Or clone manually:

```powershell
# 1. Install Graphify (AST Codebase Knowledge Graph)
pip install graphifyy
graphify install

# 2. Ensure .agents/skills exists
mkdir -p .agents/skills

# 3. Pull Ponytail (YAGNI & Anti-Bloat)
git clone https://github.com/DietrichGebert/ponytail.git .agents/skills/ponytail

# 4. Pull Prompt Master
git clone https://github.com/nidhinjs/prompt-master.git .agents/skills/prompt-master

# 5. Pull the 44 Godot Domain Skills
git clone https://github.com/thedivergentai/GD-Agentic-Skills.git .agents/skills/gd-agentic-skills
```

---

## 📦 Built-In External Skills & Repositories

| Tool / Skill | Upstream Repository | Purpose |
| :--- | :--- | :--- |
| **GD-Agentic-Skills** | [thedivergentai/GD-Agentic-Skills](https://github.com/thedivergentai/GD-Agentic-Skills) | 44 specialized Godot 4.7+ skills (RPG inventory, dialogue, combat, state machines, mobile, 2D/3D physics, shaders, etc.). |
| **Ponytail** | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | Enforces senior engineer YAGNI principles: standard library first, zero over-engineering, avoids plugin madness. |
| **Prompt Master** | [nidhinjs/prompt-master](https://github.com/nidhinjs/prompt-master) | Generates token-efficient, zero-reprompt prompts calibrated for frontier LLMs. |
| **Graphify** | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Parses AST relationships across scenes and GDScript into queryable knowledge graphs. |

---

## 🎯 Intelligent Skill Curation Matrix

When the harness bootstraps your game, it reads your folder slowly and curates from the 44 domain skills:

*   **Universal Core (Kept for all games)**:
    `godot-master`, `godot-gdscript-mastery`, `godot-project-foundations`, `godot-signal-architecture`, `godot-autoload-architecture`, `godot-scene-management`, `godot-resource-data-patterns`, `godot-ui-containers`, `godot-ui-theming`, `godot-testing-patterns`.
*   **RPG / Narrative Games**:
    Keeps `godot-inventory-system`, `godot-dialogue-system`, `godot-quest-system`, `godot-economy-system`, `godot-save-load-systems`.
*   **2D Games**:
    Keeps `godot-characterbody-2d`, `godot-2d-physics`, `godot-2d-animation`. Prunes 3D modules.
*   **3D Games**:
    Keeps 3D lighting, physics, and camera systems. Prunes 2D-only modules.
*   **Action / Platformers**:
    Keeps `godot-animation-tree-mastery`, `godot-camera-systems`, `godot-input-handling`, `godot-tweening`.
*   **Multiplayer / Mobile**:
    Kept strictly when networking (ENet, RPC) or touch/mobile configs exist; pruned otherwise to conserve context tokens.

---

## 🛠️ The Headless QA CLI (`game.py`)

The harness generates a single, zero-dependency Python CLI at your project root:

```bash
# 1. Inspect engine version, detected game genre, and test inventory
python game.py info

# 2. Capture an offscreen pixel-perfect PNG of ANY scene without opening a window
python game.py capture --scene res://scenes/ui/Inventory.tscn
python game.py capture --scene res://scenes/levels/Level1.tscn

# 3. Run headless GDScript test suites in tests/
python game.py test

# 4. Audit project for ExtResource breaks and forbidden dynamic UI code
python game.py validate
```

> **Why the isolated profile matters:**
> `game.py` routes headless execution through an isolated `APPDATA` directory (`<project>_godot_qa_profile`). You can run test suites and visual captures in your terminal continuously **while Godot Editor stays open**, without engine lockups or crashes.

---

## 📜 Scene-First UI Rules (`AGENTS.md`)

The generated `AGENTS.md` strictly binds agents to the **Scene-First** law:
1. **Never write UI in code**: No `Button.new()`, `Label.new()`, or `Control.new()` for layouts.
2. **Never override styles in code**: No `add_theme_stylebox_override()` or dynamic font size hacks in GDScript.
3. **Visually Editable**: All components, cards, dialogues, and screens must exist in `.tscn` files so they can be inspected in the Godot 2D/3D Editor.
4. **ScrollContainer Safety**: Children inside `ScrollContainer` must set `mouse_filter = 1 (Pass)` or `2 (Ignore)` so dragging is never swallowed.

---

## 🤝 Contributing

Contributions, additional domain skills, and game genre templates are welcome! Feel free to open an issue or submit a PR.

## 📄 License

Distributed under the [MIT License](LICENSE).
