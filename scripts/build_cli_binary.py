#!/usr/bin/env python3
"""Build a standalone adanos CLI binary archive with PyInstaller."""

from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_SRC = REPO_ROOT / "src"
CLI_ENTRYPOINT = REPO_ROOT / "scripts" / "pyinstaller_entrypoint.py"
PACKAGE_INIT = CLI_SRC / "adanos_cli" / "__init__.py"


def read_package_version() -> str:
    match = re.search(r'__version__\s*=\s*"([^"]+)"', PACKAGE_INIT.read_text(encoding="utf-8"))
    if match is None:
        raise RuntimeError(f"Could not read version from {PACKAGE_INIT}")
    return match.group(1)


def detect_target() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch_aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return f"{system}-{arch_aliases.get(machine, machine)}"


def build_pyinstaller_command(*, dist_dir: Path, build_dir: Path, spec_dir: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "adanos",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(CLI_SRC),
        "--hidden-import",
        "adanos",
        "--hidden-import",
        "stocksentiment",
        str(CLI_ENTRYPOINT),
    ]


def build_binary_archive(*, version: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adanos-binary-build-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        dist_dir = temp_dir / "dist"
        build_dir = temp_dir / "build"
        spec_dir = temp_dir / "spec"
        subprocess.run(
            build_pyinstaller_command(dist_dir=dist_dir, build_dir=build_dir, spec_dir=spec_dir),
            check=True,
            cwd=REPO_ROOT,
        )

        binary_path = dist_dir / "adanos"
        target = detect_target()
        archive_path = output_dir / f"adanos-cli-{version}-{target}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(binary_path, arcname="adanos")
        return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a standalone adanos CLI binary archive.")
    parser.add_argument("--version", help="Override the package version used in the archive name")
    parser.add_argument("--output-dir", default="dist-binaries")
    args = parser.parse_args()

    archive_path = build_binary_archive(
        version=args.version or read_package_version(),
        output_dir=Path(args.output_dir),
    )
    print(archive_path)


if __name__ == "__main__":
    main()
