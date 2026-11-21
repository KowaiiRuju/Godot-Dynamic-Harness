# Dynamic Cohesive Visual & Interaction Style Guide Template

> **Template Notice**: The harness is 100% style-agnostic. Before generating UI mockups or assets, **always check `.context/project_state.json` (`art_style_direction`) and `docs/art/style_guide.md`**. If the user has not chosen an art & UI style direction yet, **explicitly ask the user to decide their style direction first** and customize `docs/art/style_guide.md` from this template. The "Cozy HD Vector + 16x16 Pixel Art" tokens in Section 6 below are provided strictly as a concrete reference example.

---

## 1. Project-Derived Viewport & Scaling Strategy
- **Dynamic Resolution Discovery**:
  - Read the project's native viewport settings dynamically from `project.godot` (`display/window/size/viewport_width` and `viewport_height`) via `.context/project_state.json`.
  - Check `display/window/stretch/mode` (`canvas_items`, `viewport`, or `disabled`) and `display/window/stretch/aspect` (`keep`, `expand`, etc.) to determine whether scenes scale via integer pixel-stretching or responsive high-DPI vector layout.
- **Dynamic Texture Filtering**:
  - Check `rendering/textures/canvas_textures/default_texture_filter`:
    - `Nearest`: Align sprite movements, camera offsets, and pixel UI elements to the project's native integer pixel grid.
    - `Linear` / high-DPI: Support smooth sub-pixel transforms and high-resolution scalable vector panels.

---

## 2. Adaptive Typography & Readability Floors
- **Dynamic Scale Factors**:
  - Low-resolution pixel displays (viewport height `<= 360px`): Use crisp pixel fonts aligned to integer multiples.
  - Standard/HD displays (viewport height `>= 720px`): Enforce a minimum font size floor (`>= 14px` for captions/counts, `16px-20px` for buttons, `22px-28px` for titles) so text never blurs on desktop or mobile screens.
- **Theme-First Inheritance**:
  - Centralize fonts, colors, and `StyleBox` definitions in project `.tres` `Theme` resources or reusable `.tscn` components rather than applying ad-hoc script overrides.

---

## 3. 9-Slice (`StyleBoxTexture`) & Flat (`StyleBoxFlat`) Margin Standards
- **Measured Bezel Profiling (`bezel_profiler.py`)**:
  - When slicing 9-patch textures from a Canva MCP mockup, run `python game.py mockup-dissect --scene <scene.tscn> --mockup <mockup.png> --json --compact` so `patch_margin_*` (`texture_margin_*`) covers the full outer border + frame bezel + inner lip without stretching corners.
  - Enforce adequate `content_margin_*` (`>= 10-14px` on outer frames, `>= 6px` on inner slots/wells) so child labels and icons never collide with decorative borders.
- **Sibling Collision & Alignment Checks (`mockup-grade`)**:
  - Sibling panels and HUD trays must never overlap (`_rects_intersect == false`).
  - Paired stat bars (e.g., HP/Energy/XP `ProgressBar` siblings) should share a fixed-width label column (`custom_minimum_size.x`) so bar start/end X coordinates align cleanly.

---

## 4. Platform-Adaptive Interaction & Spatial Anchors
- **Touch & Desktop Targets**:
  - When mobile traits are active (`is_mobile == true`), keep interactive buttons and close icons `>= 44x44 px`.
  - Set decorative frames and background overlays to `mouse_filter = MOUSE_FILTER_IGNORE` or `MOUSE_FILTER_PASS` so they never swallow child clicks.
- **2D Top-Down Y-Sort & Decoupled Shadows**:
  - Where Y-sorting is used (`y_sort_enabled = true`), place entity local origins `(0, 0)` at ground contact and keep shadows on separate child nodes/shaders outside collision shapes.

---

## 5. Canva MCP Asset & Mockup Workflow
- Once the user defines their `art_style_direction`, generate reference UI mockups, panels, crests, icons, and backdrops via Canva MCP (`generate-image`, `remove-background`, `create-design`, `export-design`).
- Audit and grade every imported asset via `python game.py assets --audit --json --compact` and `python game.py assets --grade <asset.png> --t1 <fit> --t2 <style> --t3 <comp> --json --compact` (minimum passing score `>= 8.5`).

---

## 6. Illustrative Example Preset (Optional: Cozy HD Vector UI + 16x16 World Pixel Art)
*Use this section ONLY if the user explicitly selects a Cozy Pastoral / Dual-Fidelity art style; otherwise replace with the user's chosen palette and tokens:*
- **Example UI Palette**: Outer frame `#F3E5C9` (flat ivory), button/slot well `#E2CCA5` (warm parchment), dark timber border `#4C2B13` (`4px` outer frames, `3px` slots/pills, `2px` stat tracks), accent `#E8AE24` (amber) & `#48A83C` (meadow green), text `#2E1506` / `#FBF3DF`.
- **Example HD Bezel Margins (1280x720 base)**: Outer ink `5px` + bezel `22px` + inner lip `4px` -> `patch_margin_* >= 28-32px`, `content_margin_* >= 14px`; no Unicode emojis in UI labels.
- **Example World Sprite Contract**: Native `16x16` / `32x32` pixel art sprites displayed at integer nearest-neighbor scale with ground-contact shadow scenes.
