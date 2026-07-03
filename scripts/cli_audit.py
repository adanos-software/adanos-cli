"""Offline smoke audit for the installed adanos CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def _command() -> list[str]:
    adanos = shutil.which("adanos")
    if adanos:
        return [adanos]
    return [sys.executable, "-m", "adanos_cli"]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*_command(), *args], text=True, capture_output=True, check=False)


def _assert_ok(name: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        raise AssertionError(f"{name} failed with rc={result.returncode}: {result.stderr or result.stdout}")


def main() -> int:
    capabilities = _run("--output", "json", "capabilities")
    _assert_ok("capabilities json", capabilities)
    payload = json.loads(capabilities.stdout)
    assert payload["kind"] == "capabilities"
    assert payload["command"] == "capabilities"
    assert "auto" in payload["output_modes"]
    assert "--api-key-stdin" in payload["auth"]["secret_input"]

    text_capabilities = _run("--output", "text", "capabilities")
    _assert_ok("capabilities text", text_capabilities)
    assert text_capabilities.stdout.startswith("CLI capabilities")
    assert not text_capabilities.stdout.lstrip().startswith("{")

    endpoint_list = _run("endpoint", "list", "--platform", "polymarket-stocks", "--search", "stock", "--json")
    _assert_ok("endpoint list json", endpoint_list)
    endpoints = json.loads(endpoint_list.stdout)
    assert endpoints
    assert all(row["id"].startswith("polymarket-stocks") for row in endpoints)

    help_result = _run("trending", "--help")
    _assert_ok("trending help", help_result)
    assert "Examples:" in help_result.stdout

    unknown = _run("wat")
    assert unknown.returncode == 2
    assert "hint:" in unknown.stderr
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
