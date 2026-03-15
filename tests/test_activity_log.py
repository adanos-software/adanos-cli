"""Activity log module tests for the adanos CLI."""

from __future__ import annotations

import sys
from pathlib import Path


import adanos_cli.config as cli_config
from adanos_cli.activity_log import _command_name, append_activity, read_activity, sanitize_argv


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)


def test_sanitize_argv_redacts_split_api_key_flag() -> None:
    assert sanitize_argv(["--api-key", "adanos_key_secret", "capabilities"]) == [
        "--api-key",
        "<redacted>",
        "capabilities",
    ]


def test_sanitize_argv_redacts_inline_api_key_flag() -> None:
    assert sanitize_argv(["--api-key=adanos_key_secret", "capabilities"]) == [
        "--api-key=<redacted>",
        "capabilities",
    ]


def test_sanitize_argv_redacts_missing_api_key_value() -> None:
    assert sanitize_argv(["--api-key"]) == ["--api-key", "<redacted>"]


def test_command_name_skips_split_global_flag_values() -> None:
    assert _command_name(["--output", "json", "capabilities"]) == "capabilities"


def test_command_name_skips_inline_global_flag_values() -> None:
    assert _command_name(["--api-key=adanos_key_secret", "whoami"]) == "whoami"


def test_read_activity_returns_newest_first(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    append_activity(["capabilities"], source="direct", exit_code=0, duration_ms=5)
    append_activity(["whoami"], source="shell", exit_code=0, duration_ms=7)

    entries = read_activity(limit=2)
    assert entries[0]["command"] == "whoami"
    assert entries[1]["command"] == "capabilities"


def test_read_activity_filters_by_command_and_source(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    append_activity(["capabilities"], source="direct", exit_code=0, duration_ms=5)
    append_activity(["whoami"], source="shell", exit_code=0, duration_ms=7)

    assert read_activity(limit=5, command="capabilities")[0]["source"] == "direct"
    assert read_activity(limit=5, source="shell")[0]["command"] == "whoami"


def test_read_activity_skips_invalid_json_lines(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    path = cli_config.support_file_path("activity.log")
    cli_config.ensure_config_dir()
    path.write_text('{"command":"capabilities","source":"direct"}\nnot-json\n[]\n', encoding="utf-8")

    entries = read_activity(limit=5)
    assert len(entries) == 1
    assert entries[0]["command"] == "capabilities"


def test_read_activity_enforces_minimum_limit_of_one(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    append_activity(["capabilities"], source="direct", exit_code=0, duration_ms=5)
    append_activity(["whoami"], source="shell", exit_code=0, duration_ms=7)

    entries = read_activity(limit=0)
    assert len(entries) == 1
    assert entries[0]["command"] == "whoami"


def test_append_activity_marks_failed_entries(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    append_activity(["export"], source="direct", exit_code=2, duration_ms=11)

    entry = read_activity(limit=1)[0]
    assert entry["command"] == "export"
    assert entry["ok"] is False
    assert entry["exit_code"] == 2
