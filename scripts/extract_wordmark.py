"""Extract the glowing Citrine wordmark from the logo art.

The source logo has a nebula baked into it. Compositing it over the app's
own procedural nebula would show a seam and put two starfields in conflict,
so the wordmark is lifted onto transparency instead.

The technique: the wordmark is a bright cyan glow on a near-black field, so
per-pixel luminance is already an excellent alpha mask. Using it directly
preserves the soft glow falloff, which a hard-threshold cutout would destroy.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# Rec. 709 luminance weights.
_R, _G, _B = 0.2126, 0.7152, 0.0722


def alpha_from_luminance(
    image: Image.Image,
    gamma: float = 0.85,
    low: int = 0,
    high: int = 255,
) -> Image.Image:
    """Return an RGBA copy whose alpha channel is derived from luminance.

    ``gamma`` below 1.0 lifts the mid-tones so soft edges stay visible rather
    than fading out too aggressively.

    ``low``/``high`` bound a luminance *window*: everything at or below ``low``
    becomes fully transparent, everything at or above ``high`` fully opaque,
    and the band between them ramps. This exists because the real logo art has
    a bright nebula behind the wordmark, so plain luminance keeps the whole
    cloud. Measuring the source found a natural gap — the nebula tops out near
    L=150 while the letterforms sit at L=219 — and a window across that gap
    separates them. The wordmark's glow halo is lost with the cloud, and is
    reconstructed in CSS from ``--c-accent-glow`` instead, which has the
    side benefit of recolouring with the theme.
    """
    rgb = image.convert("RGB")
    # PIL expects a 4-tuple for an RGB->L conversion matrix.
    luminance = rgb.convert("L", matrix=(_R, _G, _B, 0))

    span = max(1, high - low)
    table = []
    for i in range(256):
        normalised = min(1.0, max(0.0, (i - low) / span))
        table.append(min(255, round(255 * (normalised ** gamma))))
    luminance = luminance.point(table)

    out = rgb.convert("RGBA")
    out.putalpha(luminance)

    # Zero the colour of fully-transparent pixels. They otherwise keep the
    # discarded nebula, which compresses as noise (60% of the file size) and
    # can fringe the letter edges when a renderer interpolates across them.
    black = Image.new("RGBA", out.size, (0, 0, 0, 0))
    mask = luminance.point(lambda v: 255 if v > 0 else 0)
    black.paste(out, mask=mask)
    return black


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="path to 'Citrine logo.png'")
    parser.add_argument("dest", type=Path, help="output RGBA png")
    parser.add_argument("--crop", type=int, nargs=4, metavar=("L", "T", "R", "B"),
                        help="optional crop box around the wordmark")
    parser.add_argument("--gamma", type=float, default=0.85,
                        help="alpha ramp shape within the luminance window")
    parser.add_argument("--low", type=int, default=0,
                        help="luminance at or below which alpha is 0")
    parser.add_argument("--high", type=int, default=255,
                        help="luminance at or above which alpha is 255")
    args = parser.parse_args()

    image = Image.open(args.source)
    if args.crop:
        image = image.crop(tuple(args.crop))

    result = alpha_from_luminance(image, gamma=args.gamma, low=args.low, high=args.high)
    bbox = result.getbbox()
    if bbox is not None:
        result = result.crop(bbox)
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.dest, optimize=True)
    print(f"wrote {args.dest} ({result.width}x{result.height})")


if __name__ == "__main__":
    main()
