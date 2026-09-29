"""Compile the native asset generators in ``native/``.

Citrine's launch animation is backed by two compiled tools — a C physics
solver and a C++ tree generator. They are build-time tools, not runtime
dependencies: they run on a maintainer's machine, their output is committed,
and a fresh clone never needs a compiler.

This module exists because "just run the compiler" is three different commands
on three platforms, and on Windows it is not a command at all until
``vcvars64.bat`` has rewritten the environment. Getting that wrong is the most
likely reason a regeneration attempt stalls, so the discovery is written down
once here and reused.

Usage::

    uv run --project backend python scripts/build_native.py
    uv run --project backend python scripts/build_native.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NATIVE_DIR = REPO_ROOT / "native"
BUILD_DIR = NATIVE_DIR / "build"

VSWHERE = Path(
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"


class ToolchainError(RuntimeError):
    """No usable compiler was found, or a compile failed."""


@dataclass(frozen=True)
class Target:
    """One compiled tool."""

    name: str
    source: Path
    language: str  # "c" or "c++"

    @property
    def binary(self) -> Path:
        suffix = ".exe" if sys.platform == "win32" else ""
        return BUILD_DIR / f"{self.name}{suffix}"


TARGETS: tuple[Target, ...] = (
    Target("trajectory", NATIVE_DIR / "trajectory" / "trajectory.c", "c"),
    Target("tree", NATIVE_DIR / "tree" / "tree.cpp", "c++"),
)


# --------------------------------------------------------------- toolchains


@dataclass(frozen=True)
class Toolchain:
    """A compiler plus the environment it needs to run in."""

    kind: str  # "msvc" | "unix"
    c_compiler: str
    cxx_compiler: str
    env: dict[str, str]

    def describe(self) -> str:
        return f"{self.kind} ({self.c_compiler} / {self.cxx_compiler})"


def _msvc_environment() -> dict[str, str] | None:
    """Return the environment ``vcvars64.bat`` produces, or None.

    MSVC cannot be invoked directly: ``cl.exe`` is not on PATH and does not
    work without INCLUDE and LIB being set. Rather than shelling out through a
    batch file for every compile, the batch file is run once and the
    environment it leaves behind is captured and reused.
    """
    if sys.platform != "win32":
        return None
    if not VSWHERE.exists():
        return None

    try:
        found = subprocess.run(
            [
                str(VSWHERE),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    install_path = found.stdout.strip().splitlines()
    if found.returncode != 0 or not install_path:
        return None

    vcvars = Path(install_path[0]) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.exists():
        return None

    # `set` after vcvars dumps the full environment. The marker separates it
    # from vcvars' own banner, which is not machine-readable.
    #
    # This runs through the shell as one string rather than as an argument
    # list: the list form makes Python quote the whole `call "..." && set`
    # clause as a single argument, and cmd then fails to parse the nested
    # quotes around the vcvars path.
    marker = "__CITRINE_ENV__"
    try:
        dumped = subprocess.run(
            f'call "{vcvars}" && echo {marker} && set',
            shell=True,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if dumped.returncode != 0 or marker not in dumped.stdout:
        return None

    env: dict[str, str] = {}
    for line in dumped.stdout.split(marker, 1)[1].splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            env[key] = value
    return env or None


def detect_toolchain() -> Toolchain:
    """Find a C and C++ compiler, preferring the platform-native one."""
    # A compiler already on PATH is deliberate — an active developer shell, or
    # a CI image that set one up — so it wins over discovery.
    for c_name, cxx_name in (("cc", "c++"), ("gcc", "g++"), ("clang", "clang++")):
        c_path = shutil.which(c_name)
        cxx_path = shutil.which(cxx_name)
        if c_path and cxx_path:
            return Toolchain("unix", c_path, cxx_path, dict(os.environ))

    msvc_env = _msvc_environment()
    if msvc_env is not None:
        # CreateProcess resolves a bare program name against the *calling*
        # process's PATH, not the one passed in `env`. So cl.exe has to be
        # resolved to an absolute path here or the spawn fails with "file not
        # found" despite the environment being correct.
        cl = shutil.which("cl.exe", path=msvc_env.get("PATH", ""))
        if cl:
            return Toolchain("msvc", cl, cl, msvc_env)

    existing_cl = shutil.which("cl.exe")
    if existing_cl:
        return Toolchain("msvc", existing_cl, existing_cl, dict(os.environ))

    raise ToolchainError(
        "No C/C++ compiler found.\n"
        "  Windows: install Visual Studio Build Tools with the "
        '"Desktop development with C++" workload.\n'
        "  macOS:   xcode-select --install\n"
        "  Linux:   install build-essential (or clang)\n"
        "\n"
        "A compiler is only needed to regenerate assets. The generated files "
        "are committed, so building or running Citrine does not require one."
    )


def _command(toolchain: Toolchain, target: Target) -> list[str]:
    """The compile command line for one target."""
    if toolchain.kind == "msvc":
        # /Fe: names the executable, /Fo: parks the object file in the build
        # directory instead of the repo root.
        std = "/std:c11" if target.language == "c" else "/std:c++17"
        return [
            toolchain.c_compiler,
            "/nologo",
            "/O2",
            "/W3",
            std,
            str(target.source),
            f"/Fe:{target.binary}",
            f"/Fo:{BUILD_DIR}\\",
            "/link",
            "/INCREMENTAL:NO",
        ]

    compiler = toolchain.c_compiler if target.language == "c" else toolchain.cxx_compiler
    std = "-std=c11" if target.language == "c" else "-std=c++17"
    command = [
        compiler,
        "-O2",
        "-Wall",
        "-Wextra",
        std,
        str(target.source),
        "-o",
        str(target.binary),
    ]
    if target.language == "c":
        command.append("-lm")  # trajectory.c uses hypot/exp/cos
    return command


def _is_stale(target: Target) -> bool:
    if not target.binary.exists():
        return True
    return target.source.stat().st_mtime > target.binary.stat().st_mtime


def build(target: Target, toolchain: Toolchain, *, force: bool = False) -> bool:
    """Compile one target. Returns True if the compiler actually ran."""
    if not force and not _is_stale(target):
        return False

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    command = _command(toolchain, target)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=toolchain.env,
        cwd=str(REPO_ROOT),
        check=False,
    )

    if result.returncode != 0:
        raise ToolchainError(
            f"Compiling {target.source.relative_to(REPO_ROOT)} failed "
            f"({' '.join(command)}):\n{result.stdout}\n{result.stderr}"
        )

    if not target.binary.exists():
        raise ToolchainError(
            f"{toolchain.c_compiler} reported success but {target.binary} "
            f"does not exist:\n{result.stdout}\n{result.stderr}"
        )
    return True


def build_all(*, force: bool = False, quiet: bool = False) -> dict[str, Path]:
    """Build every target. Returns a name -> binary path mapping."""
    toolchain = detect_toolchain()
    if not quiet:
        print(f"toolchain: {toolchain.describe()}", file=sys.stderr)

    binaries: dict[str, Path] = {}
    for target in TARGETS:
        rebuilt = build(target, toolchain, force=force)
        binaries[target.name] = target.binary
        if not quiet:
            state = "built" if rebuilt else "up to date"
            print(f"  {target.name}: {state} -> {target.binary}", file=sys.stderr)
    return binaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="rebuild even if the binary is current"
    )
    parser.add_argument(
        "--json", action="store_true", help="print the binary paths as JSON on stdout"
    )
    args = parser.parse_args()

    try:
        binaries = build_all(force=args.force)
    except ToolchainError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({name: str(path) for name, path in binaries.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
