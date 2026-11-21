---
name: pixel-art-gen
description: "Scripted pixel-art PNG renderer (render_pixel_art.py). For Moonveil in-game world sprites, ALWAYS load harvest-moon-sprite first to enforce FoMT 16x16/32x32 ROM dimensions and BGR555 palettes."
version: 0.1.0
---

# Pixel Art Generator

Generate pixel art PNGs from text descriptions. You design the art yourself and render it with the bundled Python script.

## Prerequisites

Before generating pixel art, ensure:

1. **Pillow** Python package is installed: `pip install Pillow`

If Pillow is missing, install it before proceeding.

## Design Process

When a user requests pixel art, follow these steps:

### Step 1: Measure Native Grid & Footprint

Distinguish between hardware tiles (`8x8`), terrain units (`16x16`), and multi-tile subject bounds:

| Subject Class | Native Grid / Footprint | Examples & Rules |
|---|---|---|
| Simple UI icons & pebbles | `8x8` to `12x12` | Pebble (`8x8`, `FoMT i0461`), heart, star, fence post (`12x12`, `i0263`) |
| Pickup items, lumber & mine rocks | `11x10` to `16x16` | Apple (`11x10`), pickup stone (`12x11`, `i0432`), chopped lumber (`12x14`, `i0262`), cave mine rock (`16x14`, `i0311`), rough boulder (`16x16`, `i0403`), wood stack (`16x16`, `i0265`) |
| Multi-tile smashable obstacles | `27x26` to `56x38` | Stump/log bundle (`27x26` -> `36x29` shatter, `i0439–440`), large boulder (`30x23` -> `32x23`, `i0064–65`), boulder ring (`56x38`, `i0061`) |
| Livestock & riders | `8x10` to `37x39` | Chick (`8x10`), chicken (`15x14`), dog (`16x11`), horse (`27x22`), sheep (`29x20`), cow (`32x23`), rider (`37x39`) |
| Multi-tile trees & buildings | `32x48` to `80x136+` | Mature maple (`32x48`), farm tree (`64x80`), forest conifer (`80x136`), fruit tree (`120x96`) |

- **Never force large subjects into `16x16`:** `16x16` is the terrain tile unit, not a universal cap on animal, boulder, stump, or tree dimensions.
- **Measure first:** Before choosing canvas bounds, compare against the actual player frame (`21x30` boy / `18x30` girl visible alpha) and record the ground-contact pivot.
- **Preserve registration:** Keep animation and destruction frames on a registered canvas anchor so feet, tools, and shattering rock/wood fragments do not jump between frames.

### Step 2: Build Semantic Palette Ramps & Dual-Material Bridge Banks

Assign colors by **material role** rather than a rigid 4–8 color ceiling (ROM sprites use **5 to 15 colors** for single subjects, **15 colors per 8x8 tile bank**, and up to **28** for multi-material composites):

1. **One ramp per material:** Separate ramps for metal head vs. wooden handle, white hide vs. peach muzzle, or pale cut sapwood (`#FFEFB5`/`#F7D600`) vs. vertical umber bark (`#BD8410`/`#7B5208`/`#523A08`).
2. **Dual-Material Bridge Banks (Tilemap Color Logic):** In FoMT tilemaps (`1,024` `8x8` tiles + `15` palette banks of 15 visible colors), any border tile where two materials meet shares a **bridge bank** containing both ramps:
   - *Grass + Slate Rock (`Map 14 Bank 5`):* 6 grass greens (`#4A9408` to `#4AEF21`) + 9 slate grays (`#425A63` to `#F7F7F7`).
   - *Water + Slate Rock (`Map 14 Bank 6`):* Replaces the 6 greens with 6 lake blues (`#2142C5` to `#DEF7FF`) while keeping the **exact same 9 slate grays** in slots 7–15 so the rock rim crosses seamlessly from grass into water.
3. **Mineable World Stones vs. Inventory Junk Ore:**
   - **Pickup Smooth Stone (`i0432`, `12x11`, 6 colors):** Smooth dome (`#635A5A` to `#DEE6D6`) with zero internal cracks.
   - **Rough Field Boulder (`i0403`, `16x16`, 14 colors):** Fills the tile (`185 px`) with sharp internal crag ridges (`#636363` to `#FFFFFF`) to signal that an upgraded Hammer is required.
   - **Cave Mine Rock (`i0311–313`, `16x14`, 6 colors):** Switches to a cool **slate-blue** ramp (`#525A63`, `#5A6B73`, `#6B8494`, `#8CA5B5`, `#A5C5CE`, `#B5DEE6`) distinct from outdoor gray rocks.
   - **Large Multi-Tile Boulder (`i0064`, `30x23`, 6 colors):** Reuses the 6-color outdoor stone ramp across 5–7 interlocking rounded rock lobes separated by `#635A5A` dark crevices.
   - **Junk Ore (`i0251`, `16x14`, 14 colors):** Inventory-only icon showing 3 small metallic nuggets; never use it as a world obstacle.
4. **Unified 6-Color Golden-Oak Wood Family:** Branches (`i0079`, `15x15`), Chopped Lumber (`i0262`, `12x14`), Fence Posts (`i0263`, `12x12`), Wood Stacks (`i0265`, `16x16`), and Multi-Tile Stump Bundles (`i0439`, `27x26`) all share one 6-color ramp: `#523A08` (deep umber crevice), `#7B5208` (bark shadow), `#BD8410` (golden oak midtone), `#E69C21` (warm amber), `#F7D600` (heartwood gold), `#FFEFB5` (sapwood cut rim).
5. See [references/pixel-art-guide.md](references/pixel-art-guide.md) for verified Harvest Moon ROM palettes and pixel-by-pixel coordinate maps.

### Step 3: Construct Sprites, Water Curves & Mountain Elevation

Follow the observed Harvest Moon ROM construction grammar:

1. **Silhouette & Negative Space** — Establish the outer staircase and preserve 1–2px transparent gaps between legs, tail hooks, ears, and boulder clusters so forms never merge into a flat block.
2. **Connected Volume Planes & Selective Colored Edges** — Group midtones into contiguous zones. Expose lighter midtones/highlights on sunlit top contours and use deep material-tinted darks (`#523A08` umber on wood, `#635A5A`/`#425A63` on stone) on undersides, overlaps, and focal landmarks. Never wrap every sprite in a uniform `#000000` sticker outline.
3. **Water Edge Curve Logic** — Never use blurred alpha gradients on shorelines. Construct curved ponds, rivers, and lakes using three rules:
   - **Stepped Diagonal Staircases (`2:1` -> `1:1` -> `1:2`):** Step 2px horizontal : 1px vertical on gentle entries, `1:1` on 45° bends, and `1:2` on steep vertical turns, reusing `8x8` corner tiles via H-flip and V-flip.
   - **Rock-Lobe Corner Masking:** Line pond/river curves with overlapping `12x10` to `16x14` rounded stone lobes (`#425A63` crevice, `#84949C` body, `#E6E6EF` top highlight) whose circular silhouettes hide the `8x8` grid steps.
   - **2px Froth Cushion & Wave Dashes:** Place a 1–2px bright cyan/white froth rim (`#ADF7FF`/`#DEF7FF` or `#EFF7F7`) where water meets rock/grass, and fill the water interior with horizontal 2–4px wave dashes (`#42BDFF`, `#3AADE6`).
4. **Mountain Slope & 3-Layer Depth Logic (`BG0 < Player < BG2`)** — Make top-down characters look physically embedded on mountains using four rules:
   - **2px Ribbed Slope Striations:** On steep mountain slopes, replace flat meadow grass with repeating 2px-tall dark forest-green contour ribs (`#085A31`, `#318421`) alternating with 2px lit green ridges (`#4A9408`, `#52B510`), angled at 45° along diagonal ridges.
   - **Frayed Grass Fringe Over Switchback Trails:** Draw winding ochre mountain paths (`#BD9C19` to `#EFDE52`) on `BG0` and overlay a 2–3px frayed green grass fringe on `BG1` along the edges (zero black outlines).
   - **Stacked Boulder Cliff Faces:** Build vertical elevation drops with `24–32px` tall stacked gray boulder walls (`#425A63` to `#F7F7F7`) capped by an overhanging green grass lip at the top crest.
   - **Three-Layer Canopy Sandwiching:** Place ground tiles and circular mottled tree shadow discs on `BG0` (below player), tree trunks (`#6B4A08` to `#B57331`) and cliff walls on `BG1` (Y-sorted with player feet), and upper tree crowns/roofs on `BG2` (rendered above the player head when walking behind trees).

### Step 4: Generate JSON Pixel Data

Create a JSON object using the sparse coordinate format. Only list non-background pixels:

```json
{
  "width": 16,
  "height": 16,
  "background": "transparent",
  "grid_lines": false,
  "pixel_size": 32,
  "pixels": [
    {"x": 3, "y": 0, "color": "#8C0000"},
    {"x": 4, "y": 0, "color": "#D60000"}
  ]
}
```

**Important rules:**
- Coordinates are 0-indexed. `x` is column (left to right), `y` is row (top to bottom).
- Use `"transparent"` background and crisp binary alpha (`0` or `255`) for sprites; never use software blur or semi-transparent anti-aliasing on exterior edges.
- Ground shadows in Moonveil are authored as separate scene nodes aligned to the foot pivot, not baked as blurry alpha halos.
- Double-check coordinates — off-by-one errors ruin pixel art.

### Step 5: Render to PNG

1. Write the JSON data to a file (e.g., `pixel_art.json`)
2. Run the render script from the project root:

```bash
python ".agents/skills/pixel-art-gen/scripts/render_pixel_art.py" pixel_art.json -o pixel_art.png
```

3. Display the result to the user using `view_file` on the output PNG file.

**Script arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `input` | Yes | - | JSON file path, or `-` for stdin |
| `-o, --output` | No | `pixel_art.png` | Output PNG file path |
| `-p, --pixel-size` | No | `32` | Size of each logical pixel in the output |
| `-g, --grid-lines` | No | off | Enable 1px grid lines at pixel boundaries |
| `--no-grid-lines` | No | - | Explicitly disable grid lines (overrides JSON) |

### Step 6: Validate & Iterate

Before finalizing any sprite or tile:
- **1x & Nearest-Neighbor Check:** Inspect at native `1x` and integer nearest-neighbor enlargement (`4x`/`8x`) over both light and dark backgrounds.
- **Terrain Seam Check (for tiles):** Test a `3x3` interior repeat plus horizontal, vertical, inner-corner, and outer-corner transitions to verify no visible grid seams or competing contrast.
- **Silhouette & Landmark Check:** Verify that eyes, beaks, tool tips, and leg gaps read immediately without relying on internal noise.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Pillow not installed` | Run `pip install Pillow` |
| Sprite looks noisy / AI-stippled | Merge scattered singletons into connected midtone planes; reserve single pixels for eyes, beaks, or specular glints |
| Sprite looks like a flat sticker | Replace uniform black outer ring with selective material-colored darks on the underside and lighter contours on the lit top |
| Terrain tile looks busy / grid-like | Reduce contrast between base pair (`~92%` of pixels) and keep high-contrast edges strictly on terrain boundaries |
| Image too small/large | Adjust `-p` pixel size (default 32) or use `-p 1` for native game export |
