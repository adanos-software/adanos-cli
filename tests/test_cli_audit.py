"""Tests for the offline CLI release audit."""

from __future__ import annotations

from scripts import cli_audit


def test_explicit_cli_command_overrides_path_discovery() -> None:
    assert cli_audit._command(["--", "/tmp/adanos", "wrapper-arg"]) == [
        "/tmp/adanos",
        "wrapper-arg",
    ]
