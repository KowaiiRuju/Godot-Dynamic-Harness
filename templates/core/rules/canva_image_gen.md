---
trigger: always_on
description: User-chosen art style direction gate and mandatory Canva MCP workflow for UI mockups, panels, icons, crests, and visual assets.
---

# Image & UI Mockup Generation Policy — User Style Gate & Canva MCP (GDH v2)

## 1. Mandatory User Art & UI Style Prompt Gate
- **Never Assume a Fixed Art Style**: Do not hardcode Cozy HD, pixel art, or any fixed aesthetic across projects.
- **Check Before Generating**: Before generating any UI mockup, panel, icon, backdrop, or sprite, inspect `art_style_direction` in `.context/project_state.json` and `docs/art/style_guide.md`.
- **Ask the User If Unset**: If `art_style_direction` is empty or unset (`ask_user_art_style: true`), **STOP and explicitly ask the user to decide and define their art & UI style direction** (palette, theme, pixel vs vector, border thickness, typography) and save their decision to `.context/project_state.json` / `docs/art/style_guide.md` first.

## 2. Canva MCP Generation Workflow
Whenever generating UI mockups, panels, crests, backdrops, icons, medallions, or illustration assets matching the user's chosen style direction, **use the Canva MCP server (`canva`) first** when enabled/available:
- **Standalone Images / Icons / Backdrops / Panels**: Call `canva:generate-image` -> poll `canva:get-generate-image-job` (if asynchronous) -> call `canva:remove-background` when transparent cutouts are required.
- **Editable Full-Screen UI Mockups & Layouts**: Use `canva:create-design` / `canva:export-design` (PNG/SVG) and save reference mockups under `.gdignore`-shielded directories (`docs/art/` or `assets/ui/staging/`).
- **Post-Processing & 5-Stage UI Pipeline**:
  1. Audit and process imported assets via `python game.py assets --audit --json --compact` and `python game.py assets --grade <asset.png> --t1 <fit> --t2 <style> --t3 <comp> --json --compact` (minimum score `>= 8.5`).
  2. Feed reference UI mockups into the 5-stage pipeline (`.agents/skills/ui-mockup-pipeline/SKILL.md`): `python game.py mockup-dissect` -> Scene-First `.tscn` authoring -> `python game.py mockup-grade` -> `python game.py capture` & `baseline --check`.
