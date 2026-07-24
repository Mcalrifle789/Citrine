"""Build the Windows application icon from the logo art.

The logo is 3:2 but an icon must be square, and squashing it would distort
the wordmark. So the art is scaled to fit and centred on a square canvas
filled with the app's background colour, which blends because the logo's own
backdrop is already near-black.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# --c-bg from src/styles/tokens.css.
BACKGROUND = (5, 3, 15, 255)

# Windows picks the nearest size; covering the range keeps the taskbar,
# Alt-Tab, and Explorer views all sharp.
ICON_SIZES = [256, 128, 64, 48, 32, 16]


def square_canvas(image: Image.Image, size: int, background=BACKGROUND) -> Image.Image:
    """Scale ``image`` to fit inside a ``size``x``size`` canvas, centred.

    Aspect ratio is preserved — the wordmark is the whole point of the icon,
    and a stretched one reads as broken.
    """
    source = image.convert("RGBA")
    scale = min(size / source.width, size / source.height)
    scaled = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.LANCZOS,
    )

    canvas = Image.new("RGBA", (size, size), background)
    canvas.alpha_composite(
        scaled,
        ((size - scaled.width) // 2, (size - scaled.height) // 2),
    )
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="path to 'Citrine logo.png'")
    parser.add_argument("dest", type=Path, help="output .ico")
    args = parser.parse_args()

    largest = square_canvas(Image.open(args.source), max(ICON_SIZES))
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    largest.save(args.dest, sizes=[(s, s) for s in ICON_SIZES])
    print(f"wrote {args.dest} ({', '.join(str(s) for s in ICON_SIZES)})")


if __name__ == "__main__":
    main()
