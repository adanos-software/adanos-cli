"""Offline smoke audit for the installed adanos CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def _command(argv: list[str] | None = None) -> list[str]:
    requested = list(sys.argv[1:] if argv is None else argv)
    if requested[:1] == ["--"]:
        requested = requested[1:]
    if requested:
        return requested
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
    for name, args in (
        ("capabilities --output json", ("--output", "json", "capabilities")),
        ("capabilities --json prefix", ("--json", "capabilities")),
        ("capabilities --json suffix", ("capabilities", "--json")),
    ):
        capabilities = _run(*args)
        _assert_ok(name, capabilities)
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

    root_help = _run("--help")
    _assert_ok("root help", root_help)
    assert "--json" in root_help.stdout

    version = _run("--version")
    _assert_ok("version", version)
    assert len(version.stdout.strip().splitlines()) == 1
    assert version.stdout.startswith("adanos-cli ")

    unknown = _run("wat")
    assert unknown.returncode == 2
    assert "hint:" in unknown.stderr

    unknown_json = _run("--json", "not-a-command")
    assert unknown_json.returncode == 2
    assert unknown_json.stdout == ""
    error_payload = json.loads(unknown_json.stderr)
    assert error_payload["error"]["code"] == "usage_error"

    nested_typo = _run("auth", "curent")
    assert nested_typo.returncode == 2
    assert "adanos auth current --help" in nested_typo.stderr
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
