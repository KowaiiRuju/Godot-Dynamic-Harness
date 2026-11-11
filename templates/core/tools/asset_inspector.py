#!/usr/bin/env python3
"""Asset creation, alpha audit, halo/fringe detection, and 3-Tier quality grading tool for Godot projects."""
import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def audit_image(image_path: Path, native_grid: int = 16) -> dict:
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not HAS_PIL:
        return {
            "file": str(image_path),
            "status": "skipped",
            "reason": "PIL / Pillow not installed in environment",
            "findings": []
        }

    findings = []
    with Image.open(image_path) as img:
        w, h = img.size
        mode = img.mode

        has_alpha = "A" in mode or mode == "RGBA"
        rgba = img.convert("RGBA") if has_alpha else None

        bbox = [0, 0, w, h]
        wasted_percent = 0.0
        fringe_count = 0
        checkerboard_detected = False

        if rgba:
            alpha = rgba.split()[-1]
            non_zero_bbox = alpha.getbbox()
            if non_zero_bbox:
                bbox = list(non_zero_bbox)
                bbox_w = bbox[2] - bbox[0]
                bbox_h = bbox[3] - bbox[1]
                wasted_area = (w * h) - (bbox_w * bbox_h)
                wasted_percent = round((wasted_area / (w * h)) * 100, 1)
                if wasted_percent > 65.0 and (w > 32 or h > 32):
                    findings.append({
                        "code": "ASSET_EXCESSIVE_PADDING",
                        "message": f"Asset has {wasted_percent}% empty padding around content (bbox: {bbox_w}x{bbox_h} in {w}x{h} canvas)",
                        "fix_hint": "Crop transparent padding: python game.py assets --process <file> --crop-alpha"
                    })

            # Detect semi-transparent border fringe
            alpha_data = list(alpha.getdata())
            # Count pixels where 5 < alpha < 240
            semi_transparent = sum(1 for a in alpha_data if 5 < a < 240)
            opaque = sum(1 for a in alpha_data if a >= 240)
            if opaque > 0:
                fringe_ratio = semi_transparent / opaque
                if fringe_ratio > 0.35:
                    findings.append({
                        "code": "ASSET_FRINGE_DETECTED",
                        "message": f"High ratio of semi-transparent halo pixels ({fringe_ratio:.2f}) indicates potential matte/edge fringe",
                        "fix_hint": "Clean matte halo: python game.py assets --process <file> --defringe"
                    })
        else:
            # Check for fake baked checkerboard in opaque image
            # Sample 16x16 blocks
            if w >= 32 and h >= 32:
                rgb = img.convert("RGB")
                pixels = rgb.load()
                # Sample corners of an 8x8 checkerboard cell
                c1 = pixels[0, 0]
                c2 = pixels[8, 0] if w > 8 else c1
                c3 = pixels[0, 8] if h > 8 else c1
                if c1 != c2 and c2 == c3 and all(abs(v - 204) < 15 for v in c1) and all(abs(v - 255) < 15 for v in c2):
                    checkerboard_detected = True
                    findings.append({
                        "code": "ASSET_BAKED_CHECKERBOARD",
                        "message": "Detected baked fake transparency checkerboard pattern instead of true alpha",
                        "fix_hint": "Remove baked background with image-bg-removal or re-export as true 32-bit RGBA PNG."
                    })

        # Grid alignment check
        if native_grid > 1:
            if w % native_grid != 0 or h % native_grid != 0:
                findings.append({
                    "code": "ASSET_NOT_GRID_ALIGNED",
                    "message": f"Dimensions ({w}x{h}) are not divisible by native grid size ({native_grid}px)",
                    "fix_hint": f"Scale or pad dimensions to multiples of {native_grid}px."
                })

        return {
            "file": str(image_path),
            "dimensions": [w, h],
            "mode": mode,
            "has_alpha": has_alpha,
            "content_bbox": bbox,
            "wasted_padding_percent": wasted_percent,
            "findings": findings
        }


def process_image(input_path: Path, output_path: Path = None, *,
                  defringe: bool = False, crop_alpha: bool = False,
                  scale: int = 1) -> dict:
    if not input_path.is_file():
        raise FileNotFoundError(f"Input image not found: {input_path}")
    if not HAS_PIL:
        raise RuntimeError("Pillow is required for asset processing")

    out_file = output_path or input_path
    actions_taken = []

    with Image.open(input_path) as img:
        work = img.convert("RGBA")

        if crop_alpha:
            alpha = work.split()[-1]
            bbox = alpha.getbbox()
            if bbox:
                work = work.crop(bbox)
                actions_taken.append(f"crop_alpha to {bbox}")

        if defringe:
            # Defringe: clamp semi-transparent pixels with low alpha to 0, high alpha to 255
            r, g, b, a = work.split()
            a_data = list(a.getdata())
            new_a = [0 if v < 20 else (255 if v > 235 else v) for v in a_data]
            a.putdata(new_a)
            work = Image.merge("RGBA", (r, g, b, a))
            actions_taken.append("defringe alpha clean")

        if scale > 1:
            nw = work.width * scale
            nh = work.height * scale
            work = work.resize((nw, nh), resample=Image.Resampling.NEAREST)
            actions_taken.append(f"nearest_neighbor scale {scale}x ({nw}x{nh})")

        out_file.parent.mkdir(parents=True, exist_ok=True)
        work.save(out_file, "PNG")

    return {
        "input": str(input_path),
        "output": str(out_file),
        "actions": actions_taken,
        "new_dimensions": [work.width, work.height]
    }


def grade_asset(image_path: Path, manifest_path: Path, scores: dict = None) -> dict:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    scores = scores or {}
    t1 = float(scores.get("tier1_hygiene", scores.get("t1", 9.0)))
    t2 = float(scores.get("tier2_artistic", scores.get("t2", 8.5)))
    t3 = float(scores.get("tier3_functional", scores.get("t3", 8.5)))
    overall = round((t1 * 0.3) + (t2 * 0.35) + (t3 * 0.35), 2)

    entry = {
        "file": str(image_path),
        "scores": {
            "tier1_technical_hygiene": t1,
            "tier2_artistic_consistency": t2,
            "tier3_functional_clarity": t3,
            "overall": overall
        },
        "passed": overall >= 8.0,
        "notes": scores.get("notes", "Automated or reviewer rubric assessment")
    }

    manifest[str(image_path.as_posix())] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return entry


def audit_project_assets(root: Path, native_grid: int = 16) -> dict:
    image_extensions = {".png", ".webp"}
    assets = [p for p in root.rglob("*") if p.suffix.lower() in image_extensions and ".harness" not in p.parts and "screenshots" not in p.parts and ".godot" not in p.parts]
    results = []
    total_findings = []
    for asset in assets:
        aud = audit_image(asset, native_grid=native_grid)
        aud["relative_path"] = str(asset.relative_to(root)).replace("\\", "/")
        results.append(aud)
        total_findings.extend(aud["findings"])

    return {
        "assets_scanned": len(assets),
        "findings_count": len(total_findings),
        "findings": total_findings,
        "results": results
    }
