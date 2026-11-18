"""
Fills the empty space round a baked texture's UV islands with the colour of the nearest
island, so that the smaller mipmaps a game samples at a distance never blend the black
background into a face, a uniform or a pouch (which shows as dark seams and smudges).

    python3 art/blender/fill_margins.py <image> [<image> ...]

Pull-push: the islands are averaged down to a single pixel, then the averages are pulled
back up level by level into every pixel that has no colour of its own. Island pixels are
kept exactly. Needs numpy and Pillow (the system Python, not Blender's).
"""
import sys

import numpy as np
from PIL import Image


def fill(rgb, known):
    """rgb: H x W x 3 floats; known: H x W booleans. Returns rgb with the unknown pixels filled."""
    levels = []
    colour = rgb * known[..., None]
    weight = known.astype(np.float64)
    while min(colour.shape[:2]) > 1:
        levels.append((colour, weight))
        h, w = colour.shape[0] // 2, colour.shape[1] // 2
        colour = colour[:h * 2, :w * 2].reshape(h, 2, w, 2, 3).sum(axis=(1, 3))
        weight = weight[:h * 2, :w * 2].reshape(h, 2, w, 2).sum(axis=(1, 3))
    filled = colour / np.maximum(weight, 1e-9)[..., None]
    for colour, weight in reversed(levels):
        h, w = colour.shape[:2]
        up = np.repeat(np.repeat(filled, 2, axis=0), 2, axis=1)[:h, :w]
        own = colour / np.maximum(weight, 1e-9)[..., None]
        filled = np.where((weight > 0)[..., None], own, up)
    return np.where(known[..., None], rgb, filled)


def main(paths):
    for path in paths:
        image = Image.open(path)
        rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
        # The bake leaves the background pure black. JPEG rings round the islands' edges with
        # near-black too; nothing the bakes paint on an island is that dark.
        jpeg = path.lower().endswith((".jpg", ".jpeg"))
        known = rgb.max(axis=2) > (48 if jpeg else 3)
        if known.all():
            print(f"{path}: nothing to fill")
            continue
        out = fill(rgb, known).clip(0, 255).astype(np.uint8)
        result = Image.fromarray(out, "RGB")
        if jpeg:
            result.save(path, quality=92)
        else:
            result.save(path)
        print(f"{path}: filled {100.0 * (1 - known.mean()):.0f}% empty space")


if __name__ == "__main__":
    main(sys.argv[1:])
