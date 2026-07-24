"""The asset scripts are build tooling, but they encode real decisions
(alpha derivation, tile seamlessness) that regress silently if untested."""

import sys
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_wordmark import alpha_from_luminance  # noqa: E402
from gen_starfield import generate_starfield  # noqa: E402


def test_alpha_from_luminance_makes_dark_pixels_transparent():
    source = Image.new("RGB", (2, 1))
    source.putpixel((0, 0), (0, 0, 0))        # background
    source.putpixel((1, 0), (92, 225, 255))   # glowing wordmark
    result = alpha_from_luminance(source)
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((1, 0))[3] > 200


def test_alpha_from_luminance_preserves_colour():
    source = Image.new("RGB", (1, 1), (92, 225, 255))
    r, g, b, _ = alpha_from_luminance(source).getpixel((0, 0))
    assert (r, g, b) == (92, 225, 255)


def test_alpha_from_luminance_ramps_glow_falloff():
    """A mid-brightness glow pixel must be partially transparent, which is
    what makes the extracted wordmark composite cleanly over any backdrop."""
    source = Image.new("RGB", (1, 1), (46, 112, 128))
    alpha = alpha_from_luminance(source).getpixel((0, 0))[3]
    assert 40 < alpha < 215


def test_luminance_window_rejects_a_bright_nebula():
    """The plan assumed a bright wordmark on a near-black field, but the real
    logo art has a genuinely bright nebula behind it. A window over the
    luminance gap (nothing lives between L=160 and L=210 in the source)
    separates letterform from cloud where a plain gamma ramp cannot."""
    nebula = Image.new("RGB", (1, 1), (23, 24, 65))       # L ~= 27
    assert alpha_from_luminance(nebula, low=190, high=222).getpixel((0, 0))[3] == 0


def test_luminance_window_keeps_the_letterform():
    letter = Image.new("RGB", (1, 1), (130, 242, 251))    # L ~= 219
    assert alpha_from_luminance(letter, low=190, high=222).getpixel((0, 0))[3] > 220


def test_luminance_window_rejects_mid_bright_cloud():
    """The brightest gold cloud in the source reaches roughly L=150 and must
    still fall entirely outside the window."""
    cloud = Image.new("RGB", (1, 1), (200, 140, 60))      # L ~= 147
    assert alpha_from_luminance(cloud, low=190, high=222).getpixel((0, 0))[3] == 0


def test_luminance_window_still_ramps_inside_the_band():
    """Edge antialiasing must stay partially transparent, or the letterforms
    acquire a hard jagged edge."""
    edge = Image.new("RGB", (1, 1), (120, 210, 220))      # L ~= 192, just inside
    alpha = alpha_from_luminance(edge, low=190, high=222).getpixel((0, 0))[3]
    assert 0 < alpha < 200


def test_fully_transparent_pixels_carry_no_colour():
    """Transparent pixels retaining their original RGB cost 60% of the file
    size (the discarded nebula still compresses as noise) and can fringe the
    letter edges when a renderer interpolates across them."""
    source = Image.new("RGB", (1, 1), (23, 24, 65))       # rejected by the window
    assert alpha_from_luminance(source, low=190, high=222).getpixel((0, 0)) == (0, 0, 0, 0)


def test_starfield_is_the_expected_size_and_mode():
    img = generate_starfield(size=512, seed=7)
    assert img.size == (512, 512)
    assert img.mode == "RGBA"


def test_starfield_is_deterministic_for_a_seed():
    assert generate_starfield(size=64, seed=3).tobytes() == \
           generate_starfield(size=64, seed=3).tobytes()


def test_starfield_differs_between_seeds():
    assert generate_starfield(size=64, seed=3).tobytes() != \
           generate_starfield(size=64, seed=4).tobytes()


def test_starfield_is_mostly_transparent():
    """Stars are sparse; a dense field reads as noise, not space."""
    img = generate_starfield(size=128, seed=11)
    alpha = img.getchannel("A").tobytes()
    opaque = sum(1 for a in alpha if a > 8)
    assert 0 < opaque < (128 * 128) * 0.05


def test_starfield_tiles_seamlessly():
    """Opposing edges must match exactly, or the repeat shows a seam."""
    img = generate_starfield(size=128, seed=5)
    px = img.load()

    left = [px[0, i][3] for i in range(128)]
    right = [px[127, i][3] for i in range(128)]
    assert left == right, "left and right edges must match"

    top = [px[i, 0][3] for i in range(128)]
    bottom = [px[i, 127][3] for i in range(128)]
    assert top == bottom, "top and bottom edges must match"
