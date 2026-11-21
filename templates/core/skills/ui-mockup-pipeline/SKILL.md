---
name: ui-mockup-pipeline
description: Style-agnostic 5-Stage Connected UI Mockup Pipeline (User Art Style Gate + Canva MCP -> mockup-dissect -> Scene-First .tscn edit -> mockup-grade -> capture & baseline). Load before any UI, HUD, menu, modal, StyleBox, or visual asset task.
---

# Connected 5-Stage UI Mockup Pipeline (GDH v2)

## 1. Style-Agnostic Principle & Reference Template
- **Never Hardcode an Art Style**: This pipeline adapts to any user-chosen aesthetic (dark sci-fi, minimalist flat vector, cozy pastoral wood/parchment, pixel art, cyberpunk, or hand-drawn 2D).
- **Style Guide Template**: See [style_guide_template.md](references/style_guide_template.md) for how to document viewport scaling, typography floors, 9-slice bezel margins, and optional dual-fidelity rules (using Cozy HD / pixel art strictly as an illustrative example).

## 2. The 5-Stage Connected Workflow

### Stage 0: Prerequisites & User Art Style Prompt Gate
1. **Check User Art & UI Style Direction**:
   - Inspect `art_style_direction` in `.context/project_state.json` and `docs/art/style_guide.md` (or run `python game.py plan-task "<ui task>" --json --compact`).
   - If `art_style_direction` is unset (`ask_user_art_style: true` or `ART_STYLE_DIRECTION_UNSET`), **STOP and explicitly ask the user to decide and define their art & UI style direction** (palette, border/bezel style, typography, resolution, pixel vs vector). Save their decision to `.context/project_state.json` and `docs/art/style_guide.md`.
2. **Generate / Export Mockups & Assets via Canva MCP**:
   - Use Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`) per `.agents/rules/canva_image_gen.md` to generate reference mockups and UI textures matching the user's chosen style.
   - Ensure staging/reference directories (`docs/`, `assets/ui/staging/`) contain a `.gdignore` file.
3. **Verify Prerequisites & Grade Assets**:
   - `python game.py mockup-dissect --check-prereqs --json --compact`
   - `python game.py assets --audit --json --compact` (and `--grade` requiring `>= 8.5` across Fit, Style, Composition).

### Stage 1: Dissect & Profile (`mockup-dissect`)
- Run 1D scanline bezel profiling (`core/tools/ui_pipeline/bezel_profiler.py`) and headless Godot control bounds probing (`core/tools/ui_pipeline/control_bounds_probe.gd`):
  ```powershell
  python game.py mockup-dissect --scene <scene.tscn> --mockup <mockup.png> --json --compact --out artifacts/ui_pipeline/dissect.json
  ```
- Writes deterministic `artifacts/ui_pipeline/dissection_manifest.json` and swarm handoff `artifacts/ui_pipeline/manifest.json` (with POSIX paths, measured bezel/border layers, and all `styled_controls`).

### Stage 2: Scene-First `.tscn` Authoring
- Author all `StyleBoxTexture` (`texture_margin_*`, `content_margin_*`) and `StyleBoxFlat` (`border_width_*`, `corner_radius_*`, `content_margin_*`) properties, container alignments, and `custom_minimum_size` directly in `.tscn` or `.tres` resources.
- **Never** instantiate UI procedurally in GDScript (`Control.new()`, `Button.new()`, `Label.new()`, `Panel.new()`).
- Verify scene and UID integrity:
  ```powershell
  python game.py validate --uid --json --compact --out .agent-state/validate.json
  ```

### Stage 3: Deterministic Grading (`mockup-grade`)
- Grade every `StyleBoxTexture` / `StyleBoxFlat` control, margin/padding threshold, sibling overlap, and progress-bar column alignment against `dissection_manifest.json`:
  ```powershell
  python game.py mockup-grade --manifest artifacts/ui_pipeline/dissection_manifest.json --json --compact --out artifacts/ui_pipeline/grade.json
  ```
- If `passed == false` (`failed_components > 0`), return to **Stage 2**, fix the reported controls in `.tscn`, re-run `mockup-dissect` and `mockup-grade` until `passed: true`.

### Stage 4: Visual Capture & Baseline Diff
- Once `mockup-grade` returns `passed: true`, follow its `next_command` directly into visual capture and layout baseline verification:
  ```powershell
  python game.py capture --scene <scene.tscn> --json --compact --out .agent-state/capture.json
  python game.py baseline --check --scene <scene.tscn> --json --compact --out .agent-state/baseline.json
  ```
