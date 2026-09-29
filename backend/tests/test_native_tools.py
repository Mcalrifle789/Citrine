"""The compiled asset generators in native/.

These tools encode physics and growth rules that no other test touches, and
their output is committed — so a regression here ships as a broken animation
rather than a failing build. The checks are behavioural invariants (it lands on
its mark, it grows as it falls, the tree reports a reachable anchor) rather than
golden output, so retuning the look does not mean rewriting the suite.

The whole module skips when no compiler is present. A compiler is a maintainer
requirement, not a contributor one: the generated assets are committed, so
building and running Citrine never needs one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_native import TARGETS, ToolchainError, build_all  # noqa: E402


@pytest.fixture(scope="module")
def binaries() -> dict[str, Path]:
    try:
        return build_all(quiet=True)
    except ToolchainError as error:
        pytest.skip(f"no C/C++ toolchain available: {str(error).splitlines()[0]}")


def _run(binary: Path, args: list[str]) -> str:
    result = subprocess.run(
        [str(binary), *args], capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def trajectory(binaries) -> dict:
    return json.loads(_run(binaries["trajectory"], []))


# --------------------------------------------------------------- trajectory


def test_trajectory_lands_exactly_on_its_resting_mark(trajectory):
    """The whole reason the launch velocity is solved rather than chosen.

    The logo has to end centred on the mark the shell's layout expects; a
    near-miss would show as a visible jump at the hand-off.
    """
    final = trajectory["frames"][-1]
    assert final["x"] == pytest.approx(trajectory["rest"]["x"], abs=1e-4)
    assert final["y"] == pytest.approx(trajectory["rest"]["y"], abs=1e-4)


def test_trajectory_starts_at_the_branch(trajectory):
    first = trajectory["frames"][0]
    assert first["x"] == pytest.approx(trajectory["anchor"]["x"], abs=1e-4)
    assert first["y"] == pytest.approx(trajectory["anchor"]["y"], abs=1e-4)


def test_the_solver_converges(trajectory):
    """A secant method that needed dozens of steps would mean the landing
    distance had stopped being monotonic in launch speed — worth knowing."""
    assert 0 < trajectory["shootIterations"] < 20


def test_the_logo_grows_from_small_to_full_size(trajectory):
    """'Starts small, grows to normal size as it falls' — the brief."""
    frames = trajectory["frames"]
    assert frames[0]["sy"] < 0.3
    assert frames[-1]["sx"] == pytest.approx(1.0, abs=1e-3)
    assert frames[-1]["sy"] == pytest.approx(1.0, abs=1e-3)


def test_growth_is_monotonic(trajectory):
    """Scale is driven by how far it has fallen, so it must never shrink —
    a wobble here would read as the logo pulsing on the way down.

    Squash-and-stretch is volume-preserving, so `sx * sy` recovers the
    underlying scale with the deformation divided back out.
    """
    import math

    frames = trajectory["frames"]
    landed_at = trajectory["landedAtMs"] / 1000.0

    # Only the descent: after touchdown the squash impulse deliberately
    # modulates the scale, which is not growth.
    scales = [
        math.sqrt(f["sx"] * f["sy"]) for f in frames if f["t"] < landed_at * 0.95
    ]
    assert scales[-1] > scales[0] * 2, "expected visible growth during the fall"

    # sx and sy go over the wire at five decimals, so their product carries a
    # rounding error of a few times 1e-6. The tolerance covers that and stays
    # far tighter than any real regression: growth here spans 0.16 to 1.0.
    for previous, current in zip(scales, scales[1:]):
        assert current >= previous - 1e-4


def test_it_bounces_before_settling(trajectory):
    assert trajectory["bounces"] >= 1


def test_it_falls_further_than_it_rises(trajectory):
    """Sanity on the physics: the arc has to end below where it started."""
    frames = trajectory["frames"]
    assert frames[-1]["y"] > frames[0]["y"]


def test_drag_makes_the_descent_steeper_than_the_ascent(trajectory):
    """The signature of quadratic drag, and the reason a solver is used at
    all — a drag-free parabola would be symmetric about its apex."""
    frames = trajectory["frames"]
    apex = min(range(len(frames)), key=lambda i: frames[i]["y"])
    landed = next(
        (i for i, f in enumerate(frames) if f["t"] * 1000 >= trajectory["landedAtMs"]),
        len(frames) - 1,
    )
    assert 0 < apex < landed, "expected a rise, an apex, then a fall"


def test_it_settles_upright(trajectory):
    """A logo that comes to rest crooked reads as a rendering bug."""
    assert trajectory["frames"][-1]["rotate"] == pytest.approx(0.0, abs=1e-6)


def test_it_fades_in_rather_than_appearing(trajectory):
    frames = trajectory["frames"]
    assert frames[0]["opacity"] == pytest.approx(0.0, abs=1e-6)
    assert frames[-1]["opacity"] == pytest.approx(1.0, abs=1e-6)


def test_frames_are_evenly_spaced_at_the_requested_rate(trajectory):
    """src/lib/launch.ts computes the bracketing frame index by division
    rather than searching, which is only valid while this holds."""
    frames = trajectory["frames"]
    step = 1.0 / trajectory["fps"]
    # The final frame is pinned to the exact settle time, so it is exempt.
    for previous, current in zip(frames, frames[1:-1]):
        assert current["t"] - previous["t"] == pytest.approx(step, abs=1e-3)


def test_trajectory_is_deterministic(binaries):
    """The output is committed, so two runs must agree byte for byte."""
    assert _run(binaries["trajectory"], []) == _run(binaries["trajectory"], [])


def test_trajectory_rejects_a_resting_point_above_the_branch(binaries):
    result = subprocess.run(
        [str(binaries["trajectory"]), "--anchor-y", "0.8", "--rest-y", "0.2"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2
    assert "must be below" in result.stderr


def test_trajectory_rejects_impossible_restitution(binaries):
    result = subprocess.run(
        [str(binaries["trajectory"]), "--restitution", "1.5"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2


def test_a_different_rest_point_is_still_hit(binaries):
    """The solver has to re-converge, not just reproduce one tuned answer."""
    data = json.loads(_run(binaries["trajectory"], ["--rest-x", "0.72"]))
    assert data["frames"][-1]["x"] == pytest.approx(0.72, abs=1e-4)


# --------------------------------------------------------------------- tree


@pytest.fixture(scope="module")
def tree_svg(binaries) -> str:
    return _run(binaries["tree"], [])


def test_tree_emits_an_svg_root(tree_svg):
    assert tree_svg.lstrip().startswith("<svg")
    assert tree_svg.rstrip().endswith("</svg>")


def test_tree_reports_an_anchor_in_stage_units(tree_svg):
    """gen_launch_assets.py reads these back to place the launch point, so
    their absence or a value off-stage would break the chained pipeline."""
    import re

    x = re.search(r'data-anchor-x="([0-9.]+)"', tree_svg)
    y = re.search(r'data-anchor-y="([0-9.]+)"', tree_svg)
    assert x and y
    assert 0.0 < float(x.group(1)) < 1.0
    assert 0.0 < float(y.group(1)) < 1.0


def test_the_anchor_is_high_in_the_canopy(tree_svg):
    """The logo has to fall. An anchor near the trunk base would leave it
    with nowhere to fall from."""
    import re

    y = float(re.search(r'data-anchor-y="([0-9.]+)"', tree_svg).group(1))
    assert y < 0.5


def test_tree_grows_branches_foliage_and_fruit(tree_svg):
    assert tree_svg.count('class="bt-branch"') > 20
    assert tree_svg.count('class="bt-leaf"') > 20
    assert tree_svg.count('class="bt-berry"') > 5


def test_tree_uses_classes_rather_than_baked_colours(tree_svg):
    """The tree recolours with the theme, which only works while the fills
    live in CSS."""
    assert "fill=\"#" not in tree_svg
    assert "stroke=\"#" not in tree_svg


def test_tree_is_deterministic_for_a_seed(binaries):
    assert _run(binaries["tree"], ["--seed", "7"]) == _run(binaries["tree"], ["--seed", "7"])


def test_different_seeds_grow_different_trees(binaries):
    assert _run(binaries["tree"], ["--seed", "1"]) != _run(binaries["tree"], ["--seed", "2"])


def test_tree_rejects_an_explosive_depth(binaries):
    """Depth is exponential in both time and output size."""
    result = subprocess.run(
        [str(binaries["tree"]), "--depth", "40"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 2


def test_every_target_builds(binaries):
    for target in TARGETS:
        assert binaries[target.name].exists()
