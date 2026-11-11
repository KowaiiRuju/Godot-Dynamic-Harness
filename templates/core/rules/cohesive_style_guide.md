# Dynamic Cohesive Visual & Interaction Style Guide

This guide provides a flexible, project-adaptive foundation for Godot 4 games. Rather than enforcing fixed aesthetic choices, the harness dynamically adapts to each project's configured display settings, viewport scale, target platforms, and custom Theme resources.

---

## 1. Project-Derived Viewport & Scaling Strategy
- **Dynamic Resolution Discovery**:
  - Always read the project's native viewport settings dynamically from `project.godot` (`display/window/size/viewport_width` and `viewport_height`), or discover them via `python game.py info --json`.
  - Check `display/window/stretch/mode` (`canvas_items`, `viewport`, or `disabled`) and `display/window/stretch/aspect` (`keep`, `expand`, etc.) to determine whether scenes scale via integer pixel-stretching or responsive vector layout.
- **Dynamic Texture Filtering**:
  - Check `rendering/textures/canvas_textures/default_texture_filter`:
    - If set to `Nearest`: Align sprite movements, camera offsets, and UI elements to the project's native integer pixel grid.
    - If set to `Linear` or high-DPI: Support smooth sub-pixel transforms and high-resolution scalable vectors.
  - Do not force a fixed grid size (e.g. 16px vs 32px); dynamically adapt to the project's authored tile and sprite dimensions.

---

## 2. Adaptive Typography & Readability
- **Dynamic Scale Factors**:
  - Base font sizes on the project's native viewport height:
    - Low-resolution pixel displays (e.g., viewport height <= 360px): Scale typography proportionately with pixel fonts and crisp pixel grid outlines.
    - Standard/High-resolution displays (viewport height >= 720px): Provide comfortable reading sizes with dynamic anti-aliasing.
- **Theme-First Inheritance**:
  - Query existing project `.tres` `Theme` resources and Godot default themes before authoring new UI.
  - If a project Theme defines typography sizes, inherit from the Theme's font configurations rather than applying hardcoded font size overrides in scripts.

---

## 3. Platform-Adaptive Interaction & Input Bounds
- **Platform-Aware Sizing**:
  - When mobile traits are detected (`traits["is_mobile"] == true` or vertical viewport aspect ratio):
    - Ensure touch targets meet minimum accessible touch dimensions (>= 44x44 points) with generous touch padding.
  - When desktop/gamepad traits are detected:
    - Allow compact desktop UI layouts, dense inventory grids, and precise cursor hover interactions.
- **Input Event Propagation**:
  - Ensure parent containers and decorative frames do not swallow child control clicks; set `mouse_filter = MOUSE_FILTER_IGNORE` or `MOUSE_FILTER_PASS` as appropriate for the hierarchy.

---

## 4. Entity Spatial Anchors & Sorting Conventions
- **Perspective & Genre Adaptation**:
  - **2D Top-Down / Isometric**: Where Y-sorting is used (`y_sort_enabled = true`), place entity local origins `(0, 0)` at the ground contact point to ensure intuitive depth sorting between characters and obstacles.
  - **2D Side-Scrolling / Platformer**: Place entity origins and collision shapes according to the project's platform physics setup (e.g., center or bottom-center).
  - **3D Spatial**: Anchor colliders and origins consistent with project kinematic and navigation standards.
- **Decoupled Visuals**:
  - Keep shadow sprites, ground rings, and selection indicators on separate child nodes or shaders so collision boundaries reflect true gameplay physics.

---

## 5. Dynamic Theme & Palette Consistency
- **Aesthetic Independence**:
  - The harness is completely agnostic to game genre and art style (whether pixel art, stylized 3D, retro sci-fi, hand-drawn 2D, or minimalist vector).
  - Always inspect the project's existing color palette, textures, and asset folders before introducing new art or styling.
- **Zero Hardcoded Overrides**:
  - Centralize colors and styling inside project `.tres` Themes or scene presets rather than hardcoding ad-hoc styling in GDScript.
- **Asset Integrity Verification**:
  - Before adopting generated or imported visual assets, audit transparency and bounding boxes (`python game.py assets --audit`) to ensure they seamlessly integrate with the project's existing rendering pipeline.
