#!/usr/bin/env python3
"""Style-agnostic 1D scanline bezel profiler for UI panels and mockups."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

DEFAULT_MEASURED_LAYERS: Dict[str, int] = {
    "outer_outline_px": 5,
    "wood_bezel_px": 22,
    "inner_lip_px": 4,
    "required_patch_margin_px": 31,
    "required_content_margin_px": 14,
    "corner_radius_px": 18,
}

# Default normalized [x0, y0, x1, y1] regions when no custom --regions-json is supplied
MOCKUP_COMPONENT_REGIONS: Dict[str, Tuple[str, Tuple[float, float, float, float]]] = {
    "HD00": ("FullHUD", (0.0, 0.0, 1.0, 1.0)),
    "HD01": ("TopLeftPanel", (0.015, 0.02, 0.40, 0.17)),
    "HD02": ("ProfileCard", (0.02, 0.025, 0.25, 0.165)),
    "HD03": ("MiniCalendarWidget", (0.255, 0.025, 0.395, 0.165)),
    "HD04": ("CampfireCompass", (0.015, 0.18, 0.28, 0.26)),
    "HD05": ("HotbarWrapper", (0.20, 0.84, 0.80, 0.98)),
    "HD06": ("Joystick", (0.03, 0.63, 0.18, 0.95)),
    "HD07": ("ActionButtons", (0.83, 0.56, 0.97, 0.96)),
    "HD08": ("TopRightUtility", (0.78, 0.02, 0.98, 0.12)),
}


def _luminance(rgb: Tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _color_distance(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _classify_pixel(rgba: Tuple[int, int, int, int]) -> str:
    r, g, b, a = rgba
    if a < 16:
        return "transparent"
    lum = _luminance((r, g, b))
    if lum < 78:
        return "outer_ink"
    if lum < 110 and r >= g >= b:
        return "inner_lip"
    if lum < 185 and r >= g >= b and (r - b) >= 20:
        return "wood_bezel"
    if lum >= 185 and r >= 200 and g >= 180:
        return "parchment"
    return "content"


def _measure_transition_bands(
    pixels: List[Tuple[int, int, int, int]],
    start_idx: int,
    threshold: float = 22.0,
) -> Optional[Dict[str, int]]:
    """Style-agnostic 1D scanline color-transition profiler for arbitrary UI art styles."""
    n = len(pixels)
    if start_idx >= n:
        return None

    bands: List[Tuple[Tuple[int, int, int, int], int]] = []
    cur_color = pixels[start_idx]
    cur_len = 0

    for idx in range(start_idx, n):
        px = pixels[idx]
        if px[3] < 16:
            break
        if _color_distance(px, cur_color) <= threshold:
            cur_len += 1
        else:
            if cur_len > 0:
                bands.append((cur_color, cur_len))
            cur_color = px
            cur_len = 1
            if len(bands) >= 5:
                break
    if cur_len > 0 and len(bands) < 5:
        bands.append((cur_color, cur_len))

    if len(bands) < 2:
        return None

    # Interpret bands from outer edge -> frame/bezel -> optional inner lip -> interior fill
    if len(bands) == 2:
        border_len = bands[0][1]
        interior_len = bands[1][1]
        if border_len <= 0 or border_len > max(64, n // 2):
            return None
        outer_ink = max(1, min(border_len // 4, 6)) if border_len >= 4 else 1
        bezel_px = max(1, border_len - outer_ink)
        inner_lip = 0
        content_pad = interior_len
    elif len(bands) == 3:
        outer_ink = bands[0][1]
        bezel_px = bands[1][1]
        inner_lip = 0
        content_pad = bands[2][1]
    else:
        outer_ink = bands[0][1]
        bezel_px = bands[1][1]
        inner_lip = bands[2][1] if bands[2][1] <= 16 else 0
        content_pad = bands[3][1] if inner_lip > 0 else bands[2][1]

    req_patch = outer_ink + bezel_px + inner_lip
    if req_patch <= 0 or req_patch > max(96, int(n * 0.75)):
        return None
    req_content = (
        max(8, min(content_pad, 24))
        if content_pad > 0
        else DEFAULT_MEASURED_LAYERS["required_content_margin_px"]
    )
    return {
        "outer_outline_px": int(outer_ink),
        "wood_bezel_px": int(bezel_px),
        "inner_lip_px": int(inner_lip),
        "required_patch_margin_px": int(req_patch),
        "required_content_margin_px": int(req_content),
        "corner_radius_px": max(4, req_patch // 2 + 2),
    }


def measure_scanline(pixels: list[Tuple[int, int, int, int]]) -> Dict[str, int]:
    """Measure outer outline, bezel/frame, inner lip, and content padding along a 1D scanline.

    Works across any UI style: supports warm wood/parchment palettes as well as arbitrary
    flat vector, dark sci-fi, minimalist, or pixel-art color transitions.
    """
    idx = 0
    n = len(pixels)
    while idx < n and _classify_pixel(pixels[idx]) == "transparent":
        idx += 1
    if idx >= n:
        return dict(DEFAULT_MEASURED_LAYERS)

    start_opaque = idx
    outer_ink = 0
    while idx < n and _classify_pixel(pixels[idx]) == "outer_ink":
        outer_ink += 1
        idx += 1

    wood_bezel = 0
    while idx < n and _classify_pixel(pixels[idx]) == "wood_bezel":
        wood_bezel += 1
        idx += 1

    inner_lip = 0
    while idx < n and _classify_pixel(pixels[idx]) in ("inner_lip", "outer_ink"):
        inner_lip += 1
        idx += 1

    content_pad = 0
    while idx < n and _classify_pixel(pixels[idx]) == "parchment":
        content_pad += 1
        idx += 1

    if outer_ink > 0 and wood_bezel > 0:
        req_patch = outer_ink + wood_bezel + inner_lip
        req_content = (
            max(14, min(content_pad, 24))
            if content_pad > 0
            else DEFAULT_MEASURED_LAYERS["required_content_margin_px"]
        )
        return {
            "outer_outline_px": outer_ink,
            "wood_bezel_px": wood_bezel,
            "inner_lip_px": inner_lip,
            "required_patch_margin_px": req_patch,
            "required_content_margin_px": req_content,
            "corner_radius_px": max(8, req_patch // 2 + 2),
        }

    # Fallback to style-agnostic color-transition band detection
    transition_layers = _measure_transition_bands(pixels, start_opaque)
    if transition_layers is not None:
        return transition_layers

    return dict(DEFAULT_MEASURED_LAYERS)


def _estimate_corner_radius(img: "Image.Image") -> int:
    w, h = img.size
    if w < 16 or h < 16:
        return DEFAULT_MEASURED_LAYERS["corner_radius_px"]
    y = 0
    while y < h // 4:
        opaque_x = next((x for x in range(w // 3) if img.getpixel((x, y))[3] >= 16), None)
        if opaque_x is not None:
            return max(4, opaque_x)
        y += 1
    return DEFAULT_MEASURED_LAYERS["corner_radius_px"]


def profile_image(
    image_path: str | Path,
    crop_box: Optional[Tuple[int, int, int, int]] = None,
) -> Dict[str, Any]:
    """Profile bezel pixel thicknesses from an image or sub-region."""
    path = Path(image_path)
    if Image is None or not path.is_file():
        return {
            **DEFAULT_MEASURED_LAYERS,
            "source": path.as_posix(),
            "measured": False,
            "note": "PIL unavailable or image missing; using calibrated fallback defaults",
        }

    with Image.open(path) as raw_img:
        img = raw_img.convert("RGBA")
        if crop_box is not None:
            img = img.crop(crop_box)
        w, h = img.size
        if w < 8 or h < 8:
            return {**DEFAULT_MEASURED_LAYERS, "source": path.as_posix(), "measured": False}

        mid_y = h // 2
        row_pixels = [img.getpixel((x, mid_y)) for x in range(w // 2)]
        h_layers = measure_scanline(row_pixels)

        mid_x = w // 2
        col_pixels = [img.getpixel((mid_x, y)) for y in range(h // 2)]
        v_layers = measure_scanline(col_pixels)

        use_layers = h_layers if h_layers["wood_bezel_px"] >= v_layers["wood_bezel_px"] else v_layers
        use_layers["corner_radius_px"] = _estimate_corner_radius(img)
        return {
            **use_layers,
            "source": path.as_posix(),
            "dimensions": [w, h],
            "measured": True,
        }


def _normalize_regions(
    custom_regions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Tuple[str, Tuple[float, float, float, float]]]:
    if not custom_regions:
        return dict(MOCKUP_COMPONENT_REGIONS)
    normalized: Dict[str, Tuple[str, Tuple[float, float, float, float]]] = {}
    for cid, spec in custom_regions.items():
        if isinstance(spec, (list, tuple)) and len(spec) == 2 and isinstance(spec[1], (list, tuple)):
            label = str(spec[0])
            coords = tuple(float(v) for v in spec[1][:4])
            if len(coords) == 4:
                normalized[str(cid)] = (label, (coords[0], coords[1], coords[2], coords[3]))
        elif isinstance(spec, dict):
            label = str(spec.get("label", cid))
            box = spec.get("box", [0.0, 0.0, 1.0, 1.0])
            if isinstance(box, (list, tuple)) and len(box) >= 4:
                normalized[str(cid)] = (label, (float(box[0]), float(box[1]), float(box[2]), float(box[3])))
    return normalized or dict(MOCKUP_COMPONENT_REGIONS)


def profile_mockup_components(
    mockup_path: str | Path,
    crops_dir: Optional[str | Path] = None,
    regions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Slice component regions from a mockup PNG and profile bezel layers."""
    path = Path(mockup_path)
    if Image is None or not path.is_file():
        return {
            "mockup_present": False,
            "mockup_path": path.as_posix(),
            "measured_layers_px": dict(DEFAULT_MEASURED_LAYERS),
            "slices": {},
        }

    out_dir = Path(crops_dir) if crops_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    region_map = _normalize_regions(regions)
    slices: Dict[str, Any] = {}
    with Image.open(path) as raw_img:
        img = raw_img.convert("RGBA")
        w, h = img.size
        for cid, (label, (nx0, ny0, nx1, ny1)) in region_map.items():
            box = (int(nx0 * w), int(ny0 * h), int(nx1 * w), int(ny1 * h))
            crop_file: Optional[str] = None
            if out_dir and cid != "HD00":
                dest = out_dir / f"{cid}_{label}.png"
                img.crop(box).save(dest)
                crop_file = dest.as_posix()
            prof = profile_image(path, crop_box=box if cid != "HD00" else None)
            slices[cid] = {
                "id": cid,
                "label": label,
                "box_px": list(box),
                "crop_path": crop_file,
                "layers_px": {k: prof[k] for k in DEFAULT_MEASURED_LAYERS},
            }

    first_non_full = next((cid for cid in slices if cid != "HD00"), "HD00")
    panel_layers = slices.get("HD01", slices.get(first_non_full, {})).get(
        "layers_px", dict(DEFAULT_MEASURED_LAYERS)
    )
    return {
        "mockup_present": True,
        "mockup_path": path.as_posix(),
        "mockup_size": [w, h],
        "measured_layers_px": panel_layers,
        "slices": slices,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Measure UI bezel pixel layers via 1D scanline")
    parser.add_argument("image", help="Path to panel or mockup PNG")
    parser.add_argument("--crops-dir", help="Optional output directory for sliced component crops")
    parser.add_argument("--mockup", action="store_true", help="Slice full HUD mockup components")
    parser.add_argument("--regions-json", help="Optional JSON file with custom normalized component regions")
    args = parser.parse_args()

    custom_regions = None
    if args.regions_json:
        reg_path = Path(args.regions_json)
        if reg_path.is_file():
            custom_regions = json.loads(reg_path.read_text(encoding="utf-8"))

    res = (
        profile_mockup_components(args.image, args.crops_dir, regions=custom_regions)
        if args.mockup
        else profile_image(args.image)
    )
    print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
