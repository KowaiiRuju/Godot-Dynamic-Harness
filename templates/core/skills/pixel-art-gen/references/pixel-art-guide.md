# Pixel Art Reference Guide

## JSON Pixel Data Schema

```json
{
  "width": 16,
  "height": 16,
  "background": "#FFFFFF",
  "grid_lines": false,
  "pixel_size": 32,
  "pixels": [
    {"x": 0, "y": 0, "color": "#FF0000"},
    {"x": 1, "y": 0, "color": "red"},
    {"x": 2, "y": 0, "color": "transparent"},
    {"x": 3, "y": 0, "color": [255, 128, 0]},
    {"x": 4, "y": 0, "color": [255, 128, 0, 200]}
  ]
}
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `width` | int | Yes | - | Grid width in logical pixels |
| `height` | int | Yes | - | Grid height in logical pixels |
| `background` | string | No | `"#FFFFFF"` | Background color (hex, named, or `"transparent"`) |
| `grid_lines` | bool | No | `false` | Draw 1px grid lines at pixel boundaries |
| `pixel_size` | int | No | `32` | Size of each logical pixel in the output PNG |
| `pixels` | array | Yes | - | Array of pixel objects (sparse — only non-background pixels) |

### Pixel Object

| Field | Type | Description |
|-------|------|-------------|
| `x` | int | Column index, 0-indexed from left |
| `y` | int | Row index, 0-indexed from top |
| `color` | string or array | Hex (`"#RRGGBB"`/`"#RRGGBBAA"`), CSS name (`"red"`), `"transparent"`, or RGB/RGBA array (`[R,G,B]`/`[R,G,B,A]`) |

## Verified Harvest Moon (FoMT / MFoMT ROM) Material Ramps

### 1. Tools: Iron & Ochre Wood (`MFoMT i0210` Hammer / `i0405` Sickle)

| Role | Hex | Usage |
|------|-----|-------|
| Wood Shadow | `#846300` | Handle underside and grip shadow |
| Wood Highlight | `#D69C00` | Lit upper edge of handle |
| Steel Deep | `#525252` | Lower/side occlusion plane of tool head |
| Steel Dark Mid | `#736B73` | Secondary shaded metal plane |
| Steel Midtone | `#8C8C8C` | Core body mass of metal head |
| Steel Light | `#ADADAD` | Upper lit bevel of blade/head |
| Steel Specular | `#CEC5CE` | 1–3px glint along top working ridge |

### 2. Produce & Crops (`MFoMT i0008` Apple / `i0474` Turnip / `i0088` Cabbage)

| Role | Hex | Usage |
|------|-----|-------|
| Stem Landmark | `#000019` | Single-pixel stem socket / deep crease landmark |
| Fruit Deep Shadow | `#8C0000` | Underside contour and lower right mass |
| Fruit Mid Red | `#D60000` | Primary lower/side transition plane |
| Fruit Bright Red | `#FF0000` | Main sunlit upper-left body volume |
| Fruit Specular | `#FF9C9C` | Compact 2–4px glossy cluster on upper-left shoulder |
| Foliage Dark | `#215210` / `#196B10` | Deep leaf crease and underside occlusion |
| Foliage Mid | `#4AA521` / `#319419` | Connected leaf body mass |
| Foliage Bright | `#73EF21` / `#5ACE29` | Sunlit leaf lobes |

### 3. Mineable World Stones vs. Cave Rocks vs. Inventory Ore

| Asset & ID | Size & Colors | Hex Palette & Structural Rule |
|---|---|---|
| **Pebble** (`FoMT i0461`) | `8x8` (`52 px`, 6 colors) | `#292929`, `#424242`, `#5A5A5A`, `#7B7B7B`, `#9C9C9C`, `#B5B5B5` — tiny compact sphere |
| **Pickup Smooth Stone** (`FoMT i0432` / `MFoMT i0443`) | `12x11` (`102 px`, 6 colors) | `#635A5A` (base dark), `#737373` (lower side), `#949494` (mid), `#ADB5AD` (upper mid), `#C5CEC5` (top plane), `#DEE6D6` (crest highlight). Smooth dome, zero cracks |
| **Rough Field Boulder** (`FoMT i0403`) | `16x16` (`185 px`, 14 colors) | `#636363`, `#737373`, `#7B7B7B`, `#7B847B`, `#8C8C8C`, `#949C94`, `#ADADAD`, `#BDBDBD`, `#C5CEC5`, `#D6D6D6`, `#DEE6DE`, `#EFF7EF`, `#F7FFF7`, `#FFFFFF` — sharp internal crag ridges signal Hammer Lv2+ obstacle |
| **Dark Mossy Boulder** (`FoMT i0462`) | `16x16` (`179 px`, 14 colors) | `#192908`, `#212910`, `#293119`, `#313A21`, `#3A4229`, `#424A31`, `#42523A`, `#4A5A42`, `#52634A`, `#5A6B52`, `#73846B`, `#949C8C`, `#ADB5AD`, `#C5D6C5` |
| **Cave Mine Rock** (`FoMT i0311–313`) | `16x14` (`175 px`, 6 colors) | Cool slate-blue ramp: `#525A63` (base), `#5A6B73` (shadow), `#6B8494` (midtone), `#8CA5B5` (upper mid), `#A5C5CE` (top plane), `#B5DEE6` (crest glint) |
| **Large Smashable Boulder** (`FoMT i0064–65`) | `30x23` (`417 px`, 6 colors) | Reuses the 6-color pickup stone ramp (`#635A5A` to `#DEE6D6`) across 5–7 interlocking rounded rock lobes |
| **Junk Ore (Inventory Only)** (`FoMT i0251`) | `16x14` (`156 px`, 14 colors) | `#6B6B6B` to `#BDBDC5` — 3 small overlapping metallic nuggets; never used as a world rock |

### 4. Unified 6-Color Golden-Oak Wood Family (`i0079` Branch, `i0262` Lumber, `i0263` Post, `i0265` Stack, `i0439` Stump)

| Role | Hex | Usage Across All Wood Sprites |
|------|-----|-------------------------------|
| Deep Bark Crevice (`A`) | `#523A08` | Underside base, vertical bark grooves, and root crevices (never pure black `#000000`) |
| Bark Shadow (`B`) | `#7B5208` | Shaded right/lower vertical bark columns and outer rim of cut top |
| Golden-Oak Midtone (`C`) | `#BD8410` | Main vertical cylinder body and inner heartwood ring |
| Warm Amber Lit Bark (`D`) | `#E69C21` | Sunlit left vertical bark strip and cut-face ring transition |
| Heartwood Gold (`E`) | `#F7D600` | Bright horizontal cut cross-section on top of lumber/stumps and log ends |
| Sapwood Rim Highlight (`F`) | `#FFEFB5` | Pale cream-yellow highlight ring around the top cut face |

### 5. Livestock: Cow & Sheep (`FoMT w1059` Cow / `w2731` Sheep)

| Role | Hex | Usage |
|------|-----|-------|
| Patch Core / Eye | `#080808` | Connected black hide patches, eyes, hoof tips |
| Patch Edge | `#4A4242` / `#8C8C8C` | Selective border around dark patches |
| White Hide Shade | `#CED6BD` | Lower belly and rear leg shadow |
| White Hide Base | `#EFF7EF` / `#FFFFFF` | Continuous barrel body volume |
| Muzzle Ramp | `#C59C84` → `#DEB59C` → `#FFDEB5` → `#FFEFDE` | Soft warm peach muzzle (never outlined in black) |
| Sheep Wool Ramp | `#8C8473` → `#BDB594` → `#DED6B5` → `#F7EFC5` → `#FFFFFF` | Scalloped wool lobes and highlight clumps |

### 6. Tilemap 16-Slot Palette Banks & Dual-Material Bridge Logic (`FoMT Map 0` & `Map 14`)

| Bank & Role | Slot 1–6 (Material A) | Slot 7–15 (Material B / Shared Bridge Ramp) |
|---|---|---|
| **Map 0 Bank 1**: Meadow Grass + Soil | `#4A9408`, `#63C510`, `#5AD619`, `#52E629` (59.4%), `#4AEF21`, `#52B510` | `#7BC510`, `#94C519`, `#ADC519`, `#C5CE29`, `#CED629`, `#E6D642` (32.8%), `#EFDE52` (59.4%), `#F7E66B`, `#FFF784` |
| **Map 0 Bank 3**: Farm Water + Cobblestone | `#10EFBD`, `#84FFDE`, `#ADFFF7`, `#6BDEEF`, `#8CE6F7`, `#6BF7FF`, `#9CFFEF`, `#BDE6FF`, `#DEEFEF` | `#9C948C`, `#ADADAD`, `#C5BDB5`, `#D6CEC5`, `#E6DED6`, `#EFF7F7` (pond/river stone rim) |
| **Map 14 Bank 2**: Mountain Ribbed Slope + Ochre Trail | `#085A31` (deep slope rib), `#318421` (mid rib), `#4A9408`, `#52B510`, `#63C510`, `#5AD619`, `#52E629` | `#6B4A08`, `#847B19`, `#AD8C19`, `#BD9C19`, `#CEAD21`, `#CEB529`, `#DECE3A`, `#EFDE52` (switchback path) |
| **Map 14 Bank 5**: Grass + Mountain Slate Boulders | `#4A9408`, `#52B510`, `#63C510`, `#5AD619`, `#52E629`, `#4AEF21` | `#425A63`, `#637384`, `#84949C`, `#9CA5AD`, `#B5BDC5`, `#C5CECE`, `#D6DEDE`, `#E6E6EF`, `#F7F7F7` |
| **Map 14 Bank 6**: Mountain Lake + Slate Boulders | `#2142C5`, `#297BD6`, `#3AADE6`, `#42BDFF`, `#ADF7FF`, `#DEF7FF` (2px shore froth) | `#425A63`, `#637384`, `#84949C`, `#9CA5AD`, `#B5BDC5`, `#C5CECE`, `#D6DEDE`, `#E6E6EF`, `#F7F7F7` (exact match to Bank 5) |

## Pixel-by-Pixel ROM Reference Maps

### 1. Apple (`MFoMT i0008`, `11x10` native crop, 5 colors, 90 opaque pixels)
- `A` = `#000019` (1 px), `B` = `#8C0000` (16 px), `C` = `#D60000` (28 px), `D` = `#FF0000` (34 px), `E` = `#FF9C9C` (11 px)
```text
    01234567890
00  ..CCC.CCC..
01  .CDDDDDDDC.
02  CDDDDADDDDC
03  CDEDDDDDDDC
04  CEEDDDDDDCB
05  CEEDDDDDDCB
06  CCEDDDDDCCB
07  .CCDDDDCCB.
08  ..CCCCCCB..
09  ...BB.BB...
```

### 2. Pickup Smooth Stone (`MFoMT i0443` / `FoMT i0432`, `12x11` native crop, 6 colors, 92 opaque pixels)
- `A` = `#635A5A` (19 px), `B` = `#737373` (17 px), `C` = `#949494` (19 px), `D` = `#ADB5AD` (12 px), `E` = `#C5CEC5` (15 px), `F` = `#DEE6D6` (10 px)
```text
    012345678901
00  ....BBBB....
01  ..BFFFFFFB..
02  .BFFFFFFFFB.
03  BFFEEEEEEDCB
04  BEEEEEEEEDCB
05  BEEEEDDDDDCB
06  BDDDDCCCCCCA
07  ACCCCCCCCCCA
08  .ACCCCCCCAA.
09  ..AAACCCAA..
10  ....AAAA....
```

### 3. Cave Mine Rock (`FoMT i0311`, `16x14` native crop, 6 slate-blue colors, 175 opaque pixels)
- `A` = `#525A63` (37 px), `B` = `#5A6B73` (28 px), `C` = `#6B8494` (37 px), `D` = `#8CA5B5` (32 px), `E` = `#A5C5CE` (24 px), `F` = `#B5DEE6` (17 px)
```text
    0123456789012345
00  .....CC.........
01  ....CDDCC..BB...
02  ...CDDDDDCCCCB..
03  ..CDEDDEEDDCCB..
04  ..BEEDEFFEDDCCB.
05  .BCEEEFFFFEDDCB.
06  .BCDEFFFFFEEDCA.
07  BCDDEFFFFEEDCBAA
08  BCDDEEFFEEDDCBAA
09  ABCCDEEEDDCCCBAA
10  AABCCDDDCCCBBAAA
11  .ABBBCCCCBBAAAA.
12  .AAABBBBBAAAAAA.
13  ...AAAAAAAAAA...
```

### 4. Rough 16x16 Field Boulder (`FoMT i0403`, `16x16` native crop, 14 colors, 185 opaque pixels)
- `A`=`#636363`(12), `B`=`#737373`(14), `C`=`#7B7B7B`(15), `D`=`#7B847B`(21), `E`=`#8C8C8C`(26), `F`=`#949C94`(22), `G`=`#ADADAD`(12), `H`=`#BDBDBD`(5), `I`=`#C5CEC5`(11), `J`=`#D6D6D6`(15), `K`=`#DEE6DE`(8), `L`=`#EFF7EF`(4), `M`=`#F7FFF7`(3), `N`=`#FFFFFF`(17)
```text
    0123456789012345
00  ......BEJE......
01  ...CGDBBEBGE....
02  ..DEDICEJDGE....
03  .DEGFFEGDCCIE...
04  .EEHNMLJEECIB...
05  .DFFINNNIHDFFE..
06  .DDJGNNJJNIKEBC.
07  AFDGFNEDKNJBIGC.
08  DDDCBDCBGJFDBKDF
09  DBFCIHENNJKGJFFB
10  AAECHJNNNKNKFEEE
11  .AICCFJLMKNMCDEA
12  ..AEFGILIHFGEBA.
13  ...AFJFNLEJFA...
14  ....DFJFKCA.....
15  ......AAB.......
```

### 5. Chopped Lumber Piece (`FoMT i0262`, `12x14` native crop, 6 golden-oak colors, 152 opaque pixels)
- `A` = `#523A08` (18 px), `B` = `#7B5208` (39 px), `C` = `#BD8410` (28 px), `D` = `#E69C21` (26 px), `E` = `#F7D600` (30 px), `F` = `#FFEFB5` (11 px)
```text
    012345678901
00  ...DEEEED...
01  .DEFEEEEEED.
02  DEFEEFFEDFED
03  CEFDFEEFDFEC
04  BDEEDFFEEEDB
05  BBDEEEEEDDBA
06  BBCCBCDBCBA
07  BBCBBDDCBCAB
08  ACCBCDCCDBAA
09  ABBDCDCDBBBA
10  ABBDCCCBCCAA
11  BBCCCDBBABAB
12  .BBCDCBCAAB.
13  ...BBAAAB...
```

## Unified Construction Rules for Terrain, Water, Mountains, Stones & Wood

1. **Grid & Proportions**: Use `16x16` as the world terrain unit, but let objects occupy their natural footprint (`8x8` pebble, `12x11` pickup stone, `12x14` lumber, `16x14` cave rock, `16x16` rough boulder, `27x26` stump, `30x23` large boulder, `32x23` cow, `64x80` tree).
2. **Selective Colored Outlines**: Never wrap every sprite in a uniform black border. Expose midtones/highlights on sunlit top edges and reserve material-tinted darks (`#523A08` on wood, `#635A5A`/`#425A63` on rock) for undersides, overlaps, and focal landmarks.
3. **Water Edge Curves**: Build curves with stepped diagonals (`2:1` -> `1:1` -> `1:2`), mask grid steps with overlapping `12x10`–`16x14` rounded stone lobes, and place a 1–2px bright froth rim (`#ADF7FF`/`#DEF7FF`/`#EFF7F7`) between the rock base and horizontal water wave dashes.
4. **Mountain Elevation & 3-Layer Depth (`BG0 < Player < BG2`)**: Use 2px dark/light green contour striations (`#085A31`/`#318421` vs `#4A9408`/`#52B510`) on steep slopes, frayed `BG1` grass fringes over ochre switchback paths, stacked boulder cliff walls, and `BG2` overhead tree canopies so the player walks "inside" the mountain environment.
5. **Terrain Quietness & 3x3 Seam Testing**: Keep walkable ground `~92%` within two close base tones (`152 + 84 = 236/256 px`) and test a `3x3` repeat plus all edge/corner joins.


