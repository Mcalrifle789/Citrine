"""Generate a seamlessly tileable starfield.

Procedural rather than photographic so the backdrop stays a few KB and can
be recoloured by the theme. Seeded for reproducible builds.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image

STAR_DENSITY = 0.0022  # stars per pixel — sparse enough to read as space


def generate_starfield(size: int = 512, seed: int = 1337) -> Image.Image:
    """Return an RGBA tile of white stars on full transparency.

    Stars are drawn as single pixels with a dim neighbour cross so they
    survive downscaling. Column 0 is copied to column ``size - 1`` (and the
    same for rows) so opposing edges match exactly and the tile is seamless.
    """
    rng = random.Random(seed)
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    px = img.load()

    count = int(size * size * STAR_DENSITY)
    for _ in range(count):
        x = rng.randrange(1, size - 1)
        y = rng.randrange(1, size - 1)
        brightness = rng.randint(90, 255)
        px[x, y] = (255, 255, 255, brightness)
        halo = brightness // 5
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            hx, hy = x + dx, y + dy
            if px[hx, hy][3] < halo:
                px[hx, hy] = (255, 255, 255, halo)

    # Make opposing edges identical so the tile repeats without a visible seam.
    for i in range(size):
        px[size - 1, i] = px[0, i]
        px[i, size - 1] = px[i, 0]

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    img = generate_starfield(size=args.size, seed=args.seed)
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.dest)
    print(f"wrote {args.dest} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
