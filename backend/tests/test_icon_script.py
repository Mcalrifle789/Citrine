"""The icon script squares a 3:2 logo; getting that wrong distorts the
wordmark in every taskbar and Alt-Tab view, so the fit logic is tested."""

import sys
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_icon import square_canvas  # noqa: E402


def test_output_is_square_at_the_requested_size():
    result = square_canvas(Image.new("RGB", (1536, 1024)), 256)
    assert result.size == (256, 256)


def test_wide_source_is_letterboxed_not_stretched():
    """A 2:1 source scaled into 256 must stay 2:1 — 256 wide, 128 tall — with
    the remaining height filled by the background."""
    source = Image.new("RGB", (200, 100), (92, 225, 255))
    result = square_canvas(source, 256)
    # Centre row sits inside the artwork; top row is padding.
    assert result.getpixel((128, 128))[:3] == (92, 225, 255)
    assert result.getpixel((128, 2))[:3] == (5, 3, 15)


def test_tall_source_is_letterboxed_on_the_sides():
    source = Image.new("RGB", (100, 200), (92, 225, 255))
    result = square_canvas(source, 256)
    assert result.getpixel((128, 128))[:3] == (92, 225, 255)
    assert result.getpixel((2, 128))[:3] == (5, 3, 15)


def test_result_is_fully_opaque_so_the_icon_has_no_holes():
    result = square_canvas(Image.new("RGB", (1536, 1024)), 64)
    alpha = result.getchannel("A").tobytes()
    assert min(alpha) == 255
