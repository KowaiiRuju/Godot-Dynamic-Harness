---
name: image-bg-removal
description: Use when separating foreground subjects from image backgrounds, generating transparent PNGs, or processing game assets with Pillow and transparent-background (InSPyReNet)
---

# Image Background & Subject Separation Skill

Use this workflow to remove backgrounds, isolate foreground subjects, and generate clean, transparent PNG sprites and UI icons for game development.

## 1. Environment & Setup

```bash
pip install transparent-background pillow
```

## 2. Python API Usage

```python
from PIL import Image
from transparent_background import Remover

remover = Remover(mode='base', jit=False)

def remove_background(input_path: str, output_path: str) -> None:
    img = Image.open(input_path).convert('RGB')
    out = remover.process(img, type='rgba')
    out.save(output_path, format='PNG')
```

## 3. Mandatory 3-Tier Image Grading Rubric

Before adopting any generated image into the game codebase:
1. **Fit on Game (1–10)**:
   - Does it match the game's theme and art style?
   - Perspective alignment (3/4 top-down for overworld objects, orthographic for UI icons).
2. **Style (1–10)**:
   - Palette compliance and tonal harmony.
   - Crisp outlines and shading without blurry AI artifacts.
3. **Composition (1–10)**:
   - Centering, clean silhouette, and readable details at target viewport scale.
   - 100% clean alpha transparency (zero matte fringing or ghost pixels).
