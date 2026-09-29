"""Generate the assets behind Citrine's launch animation.

Runs the two native tools and writes what the renderer consumes:

    native/tree/tree.cpp        -> src/assets/blueberry-tree.svg
    native/trajectory/trajectory.c -> src/generated/launchTrajectory.ts

The two are chained rather than run independently. The tree generator picks
which branch tip the logo departs from and reports it on the SVG root; this
script reads that back and passes it to the trajectory solver as the launch
point. So re-growing the tree with a different seed automatically re-solves the
flight to start from wherever the new branch ended up, and the two assets
cannot drift out of agreement.

Both outputs are committed, following the convention in scripts/README.md: a
fresh clone builds and runs Citrine without a C compiler.

Usage::

    uv run --project backend python scripts/gen_launch_assets.py
    uv run --project backend python scripts/gen_launch_assets.py --seed 42 --check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_native import ToolchainError, build_all  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TREE_SVG = REPO_ROOT / "src" / "assets" / "blueberry-tree.svg"
TRAJECTORY_TS = REPO_ROOT / "src" / "generated" / "launchTrajectory.ts"

# The stage the animation plays on. Width/height, matched by .ct-launch__stage
# in launch.css — the solver works in these units, so the two must agree.
STAGE_ASPECT = 1.60

# Where the logo comes to rest, in stage units. Slightly above centre so the
# settled logo sits where the shell's header will be.
REST_X = 0.50
REST_Y = 0.62


class GenerationError(RuntimeError):
    """A generator failed, or produced output that could not be parsed."""


def _run(binary: Path, args: list[str]) -> str:
    """Run a generator and return its stdout, surfacing failures with stderr."""
    result = subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise GenerationError(
            f"{binary.name} exited {result.returncode}:\n{result.stderr.strip()}"
        )
    if not result.stdout.strip():
        raise GenerationError(f"{binary.name} produced no output")

    # The tools report their statistics on stderr; worth seeing.
    if result.stderr.strip():
        print(f"  {result.stderr.strip()}", file=sys.stderr)
    return result.stdout


def _parse_anchor(svg: str) -> tuple[float, float]:
    """Read the release point the tree generator chose off the SVG root."""
    x = re.search(r'data-anchor-x="([0-9.eE+-]+)"', svg)
    y = re.search(r'data-anchor-y="([0-9.eE+-]+)"', svg)
    if not x or not y:
        raise GenerationError(
            "the tree SVG has no data-anchor-x/data-anchor-y on its root element; "
            "native/tree/tree.cpp should always emit them"
        )
    return float(x.group(1)), float(y.group(1))


def _render_trajectory_module(trajectory: dict[str, object], seed: int) -> str:
    """Render the solver's JSON as a typed TypeScript module."""
    frames = trajectory["frames"]
    if not isinstance(frames, list) or not frames:
        raise GenerationError("the trajectory solver produced no frames")

    lines = [
        "/*",
        " * GENERATED FILE — do not edit by hand.",
        " *",
        " * Produced by scripts/gen_launch_assets.py from the physics solver in",
        " * native/trajectory/trajectory.c. Regenerate with:",
        " *",
        " *   uv run --project backend python scripts/gen_launch_assets.py",
        " *",
        " * Positions are normalised stage units: x and y both in [0, 1], y down.",
        " * `sx` and `sy` are separate so squash-and-stretch can be non-uniform.",
        " */",
        "",
        "export interface LaunchFrame {",
        "  /** Seconds since release. */",
        "  t: number",
        "  x: number",
        "  y: number",
        "  sx: number",
        "  sy: number",
        "  /** Degrees. */",
        "  rotate: number",
        "  opacity: number",
        "}",
        "",
        "export interface LaunchTrajectory {",
        "  fps: number",
        "  durationMs: number",
        "  /** When the logo first touches down — the beat the tree reacts on. */",
        "  landedAtMs: number",
        "  bounces: number",
        "  /** Stage width / height the solver assumed. */",
        "  aspect: number",
        "  /** The branch tip the logo departs from. */",
        "  anchor: { x: number; y: number }",
        "  /** Where it comes to rest. */",
        "  rest: { x: number; y: number }",
        "  frames: LaunchFrame[]",
        "}",
        "",
        f"/** Grown from seed {seed}. */",
        "export const LAUNCH_TRAJECTORY: LaunchTrajectory = {",
        f"  fps: {float(trajectory['fps']):g},",
        f"  durationMs: {float(trajectory['durationMs']):g},",
        f"  landedAtMs: {float(trajectory['landedAtMs']):g},",
        f"  bounces: {int(trajectory['bounces'])},",
        f"  aspect: {float(trajectory['aspect']):g},",
        _point("anchor", trajectory["anchor"]),
        _point("rest", trajectory["rest"]),
        "  frames: [",
    ]

    for frame in frames:
        lines.append(
            "    {{ t: {t:g}, x: {x:g}, y: {y:g}, sx: {sx:g}, sy: {sy:g}, "
            "rotate: {rotate:g}, opacity: {opacity:g} }},".format(**frame)
        )

    lines += ["  ],", "}", ""]
    return "\n".join(lines)


def _point(name: str, value: object) -> str:
    if not isinstance(value, dict):
        raise GenerationError(f"trajectory.{name} is not an object")
    return f"  {name}: {{ x: {float(value['x']):g}, y: {float(value['y']):g} }},"


def _write(path: Path, content: str, *, check: bool) -> bool:
    """Write `content` to `path`. Returns True if the file changed.

    In check mode nothing is written; the return value reports whether the
    committed asset is stale.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def generate(*, seed: int, fps: float, depth: int, check: bool) -> list[Path]:
    """Build the tools, run them, write the assets. Returns changed paths."""
    binaries = build_all()

    print("growing the tree...", file=sys.stderr)
    svg = _run(
        binaries["tree"],
        [
            "--seed", str(seed),
            "--depth", str(depth),
            "--width", f"{1000 * STAGE_ASPECT:.0f}",
            "--height", "1000",
        ],
    )
    anchor_x, anchor_y = _parse_anchor(svg)

    print(
        f"solving the flight from ({anchor_x:.4f}, {anchor_y:.4f})...",
        file=sys.stderr,
    )
    raw = _run(
        binaries["trajectory"],
        [
            "--anchor-x", f"{anchor_x:.6f}",
            "--anchor-y", f"{anchor_y:.6f}",
            "--rest-x", f"{REST_X}",
            "--rest-y", f"{REST_Y}",
            "--fps", f"{fps:g}",
            "--aspect", f"{STAGE_ASPECT}",
        ],
    )

    try:
        trajectory = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GenerationError(f"the trajectory solver emitted invalid JSON: {error}")

    changed: list[Path] = []
    if _write(TREE_SVG, svg, check=check):
        changed.append(TREE_SVG)
    if _write(TRAJECTORY_TS, _render_trajectory_module(trajectory, seed), check=check):
        changed.append(TRAJECTORY_TS)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260929, help="tree growth seed")
    parser.add_argument("--fps", type=float, default=60.0, help="trajectory sample rate")
    parser.add_argument("--depth", type=int, default=6, help="tree recursion depth")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit non-zero if the committed assets are stale",
    )
    args = parser.parse_args()

    try:
        changed = generate(
            seed=args.seed, fps=args.fps, depth=args.depth, check=args.check
        )
    except (ToolchainError, GenerationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.check:
        if changed:
            for path in changed:
                print(f"stale: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        print("launch assets are up to date", file=sys.stderr)
        return 0

    if not changed:
        print("launch assets already up to date", file=sys.stderr)
    for path in changed:
        size = path.stat().st_size
        print(f"wrote {path.relative_to(REPO_ROOT)} ({size:,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
