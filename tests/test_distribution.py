"""Distribution helper tests for CLI release scripts."""

from __future__ import annotations

import sys
from pathlib import Path

from adanos_cli import __version__
import scripts.generate_homebrew_formula as homebrew_formula
from scripts.build_cli_binary import CLI_ENTRYPOINT, CLI_SRC, build_pyinstaller_command, detect_target, read_package_version
from scripts.generate_homebrew_formula import render_formula

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_render_formula_includes_all_targets() -> None:
    formula = render_formula(
        version="1.20.0",
        darwin_arm64_url="https://example.com/arm64.tar.gz",
        darwin_arm64_sha256="a" * 64,
        darwin_x86_64_url="https://example.com/x64.tar.gz",
        darwin_x86_64_sha256="b" * 64,
        linux_x86_64_url="https://example.com/linux.tar.gz",
        linux_x86_64_sha256="c" * 64,
    )
    assert 'version "1.20.0"' in formula
    assert "arm64.tar.gz" in formula
    assert "x64.tar.gz" in formula
    assert "linux.tar.gz" in formula
    assert 'bin.install "adanos"' in formula


def test_detect_target_normalizes_arch_aliases(monkeypatch) -> None:
    monkeypatch.setattr("scripts.build_cli_binary.platform.system", lambda: "Darwin")
    monkeypatch.setattr("scripts.build_cli_binary.platform.machine", lambda: "AMD64")
    assert detect_target() == "darwin-x86_64"


def test_detect_target_supports_arm64(monkeypatch) -> None:
    monkeypatch.setattr("scripts.build_cli_binary.platform.system", lambda: "Linux")
    monkeypatch.setattr("scripts.build_cli_binary.platform.machine", lambda: "aarch64")
    assert detect_target() == "linux-arm64"


def test_detect_target_preserves_unknown_arch(monkeypatch) -> None:
    monkeypatch.setattr("scripts.build_cli_binary.platform.system", lambda: "Linux")
    monkeypatch.setattr("scripts.build_cli_binary.platform.machine", lambda: "riscv64")
    assert detect_target() == "linux-riscv64"


def test_read_package_version_matches_cli_package() -> None:
    assert read_package_version() == __version__


def test_build_pyinstaller_command_uses_repo_local_paths(tmp_path) -> None:
    command = build_pyinstaller_command(
        dist_dir=tmp_path / "dist",
        build_dir=tmp_path / "build",
        spec_dir=tmp_path / "spec",
    )

    assert "--paths" in command
    assert str(CLI_SRC) in command
    assert str(CLI_ENTRYPOINT) == command[-1]
    assert "stocksentiment" in command


def test_render_formula_includes_install_and_test_blocks() -> None:
    formula = render_formula(
        version="1.20.0",
        darwin_arm64_url="https://example.com/arm64.tar.gz",
        darwin_arm64_sha256="a" * 64,
        darwin_x86_64_url="https://example.com/x64.tar.gz",
        darwin_x86_64_sha256="b" * 64,
        linux_x86_64_url="https://example.com/linux.tar.gz",
        linux_x86_64_sha256="c" * 64,
    )

    assert "class AdanosCli < Formula" in formula
    assert 'homepage "https://adanos.org"' in formula
    assert "def install" in formula
    assert 'assert_match "adanos"' in formula


def test_homebrew_formula_main_writes_output_file(tmp_path, monkeypatch) -> None:
    output_path = tmp_path / "adanos-cli.rb"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_homebrew_formula.py",
            "--version",
            "1.20.0",
            "--darwin-arm64-url",
            "https://example.com/arm64.tar.gz",
            "--darwin-arm64-sha256",
            "a" * 64,
            "--darwin-x86_64-url",
            "https://example.com/x64.tar.gz",
            "--darwin-x86_64-sha256",
            "b" * 64,
            "--linux-x86_64-url",
            "https://example.com/linux.tar.gz",
            "--linux-x86_64-sha256",
            "c" * 64,
            "--output",
            str(output_path),
        ],
    )

    homebrew_formula.main()

    assert output_path.exists()
    assert 'version "1.20.0"' in output_path.read_text(encoding="utf-8")


def test_install_shell_script_uses_latest_release_assets() -> None:
    script = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "adanos-software/adanos-cli" in script
    assert "releases/latest/download" in script
    assert "SHA256SUMS.txt" in script
    assert "adanos-darwin-arm64.tar.gz" in script
    assert "adanos-darwin-x86_64.tar.gz" in script
    assert "adanos-linux-x86_64.tar.gz" in script
    assert "ADANOS_INSTALL_DIR" in script


def test_install_powershell_script_bootstraps_pipx() -> None:
    script = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "adanos-cli" in script
    assert "pipx" in script
    assert "install --force" in script
    assert "Verify with:" in script


def test_readme_documents_shell_homebrew_and_powershell_install() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "curl -fsSL https://raw.githubusercontent.com/adanos-software/adanos-cli/main/install.sh | bash" in readme
    assert "brew install adanos-software/tap/adanos-cli" in readme
    assert "irm https://raw.githubusercontent.com/adanos-software/adanos-cli/main/install.ps1 | iex" in readme
