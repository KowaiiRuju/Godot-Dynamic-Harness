#!/usr/bin/env python3
"""Labeled HTML gallery and bounded six-scene PNG contact sheets."""
import html
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote


def write_gallery(captures, directory):
    directory = Path(directory)
    cards = []
    for index, capture in enumerate(captures, 1):
        label = html.escape(f"{index}. {capture['scene']}")
        if capture["status"] == "success":
            image = Path(capture["artifacts"][0]).relative_to(directory).as_posix()
            url = quote(image)
            content = f'<a href="{url}"><img loading="lazy" src="{url}" alt="{label}"></a>'
        else:
            message = capture["findings"][0]["message"] if capture["findings"] else capture["summary"]
            content = '<p class="failed">' + html.escape(message) + "</p>"
        cards.append(f'<article><h2 title="{label}">{label}</h2>{content}</article>')
    page = directory / "gallery.html"
    page.write_text("""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Godot scene review</title>
<style>body{margin:16px;background:#15151b;color:#eee;font:14px system-ui}main{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
article{background:#25252d;border:1px solid #454550}h1{font-size:20px}h2{font-size:12px;padding:6px;margin:0;overflow-wrap:anywhere}
img{display:block;width:100%;height:auto;max-height:640px;object-fit:contain}.failed{color:#ff9898;min-height:180px;padding:16px}
a{color:inherit}a:focus-visible{outline:3px solid #88bbff}@media(max-width:760px){main{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:440px){main{grid-template-columns:1fr}}</style>
<h1>Scene review</h1><p>Click a capture to open the full-resolution PNG. Failed scenes are shown without stopping the batch.</p><main>""" +
                    "".join(cards) + "</main></html>", encoding="utf-8")
    return page


def write_sheets(captures, directory):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"), 13)
    except OSError:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 13)
        except OSError:
            font = ImageFont.load_default()
    sheets = []
    for page, offset in enumerate(range(0, len(captures), 6), 1):
        group = captures[offset:offset + 6]
        previews = []
        for capture in group:
            if capture["status"] == "success":
                with Image.open(capture["artifacts"][0]) as source:
                    preview = source.convert("RGB")
                    preview.thumbnail((320, 640), Image.Resampling.LANCZOS)
                previews.append(preview)
            else:
                previews.append(None)
        height = max([preview.height for preview in previews if preview is not None] or [180])
        columns = min(3, len(group))
        rows = (len(group) + columns - 1) // columns
        gutter, header, width = 8, 28, 320
        canvas = Image.new("RGB", (gutter + columns * (width + gutter), gutter + rows * (height + header + gutter)), "#15151b")
        draw = ImageDraw.Draw(canvas)
        for index, (capture, preview) in enumerate(zip(group, previews)):
            x = gutter + (index % columns) * (width + gutter)
            y = gutter + (index // columns) * (height + header + gutter)
            label = f"{offset + index + 1}. {capture['scene']}"
            # Full Unicode paths remain available in the gallery/manifest if a fallback font lacks glyphs.
            try:
                while draw.textbbox((0, 0), label, font=font)[2] > width - 12:
                    label = label[:-2] + "\u2026"
                draw.text((x + 6, y + 6), label, font=font, fill="white")
            except UnicodeError:
                draw.text((x + 6, y + 6), label.encode("ascii", "replace").decode(), font=font, fill="white")
            if preview is not None:
                canvas.paste(preview, (x + (width - preview.width) // 2, y + header))
            else:
                draw.rectangle((x, y + header, x + width - 1, y + header + height - 1), fill="#3b2024")
                draw.text((x + 12, y + header + 24), "CAPTURE FAILED - see gallery", font=font, fill="#ffaaaa")
        target = Path(directory) / f"contact_sheet_{page:03d}.png"
        canvas.save(target)
        sheets.append(target)
    return sheets


def export(captures, directory):
    gallery = write_gallery(captures, directory)
    try:
        sheets = write_sheets(captures, directory)
        return {"artifacts": [str(gallery), *map(str, sheets)], "png_grid": "available", "scenes_per_sheet": 6, "columns": 3}
    except ImportError:
        return {"artifacts": [str(gallery)], "png_grid": "unavailable", "note": "HTML gallery is ready. Propose Pillow installation with bootstrap --png-grid for PNG contact sheets."}


def main():
    report = Path(sys.argv[1]).resolve()
    try:
        output = export(json.loads(report.read_text(encoding="utf-8")), report.parent)
        print(json.dumps(output))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
