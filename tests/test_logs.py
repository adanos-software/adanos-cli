"""Activity log and logs command tests for the adanos CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path


import adanos_cli.config as cli_config
import adanos_cli.main as cli_main
from adanos_cli.activity_log import read_activity


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)
    monkeypatch.setenv("ADANOS_CLI_DISABLE_UPDATE_CHECK", "1")


def test_logs_path_and_tail_json(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    assert cli_main.main(["--output", "json", "capabilities"]) == 0
    capsys.readouterr()

    rc = cli_main.main(["logs", "path", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "logs_path"

    rc = cli_main.main(["logs", "tail", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "logs_tail"
    assert payload["entries"][0]["command"] == "capabilities"
    assert payload["entries"][0]["source"] == "direct"


def test_logs_path_text_mode_prints_file_path(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(["logs", "path"])
    out = capsys.readouterr().out.strip()

    assert rc == 0
    assert out.endswith("activity.log")


def test_logs_tail_does_not_log_itself(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    assert cli_main.main(["--output", "json", "capabilities"]) == 0
    capsys.readouterr()

    assert cli_main.main(["logs", "tail", "--json"]) == 0
    first_payload = json.loads(capsys.readouterr().out)
    assert len(first_payload["entries"]) == 1

    assert cli_main.main(["logs", "tail", "--json"]) == 0
    second_payload = json.loads(capsys.readouterr().out)
    assert len(second_payload["entries"]) == 1
    assert second_payload["entries"][0]["command"] == "capabilities"


def test_logs_tail_text_mode_reports_empty_state(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(["logs", "tail"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "No CLI activity logs yet." in out


def test_logs_redact_api_key_flags(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(["--api-key", "adanos_key_secret_abcdefghijklmnopqrstuvwxyz", "--output", "json", "capabilities"])
    assert rc == 0
    capsys.readouterr()

    entries = read_activity(limit=5)
    assert entries[0]["argv"][0] == "--api-key"
    assert "<redacted>" in entries[0]["argv"]


def test_logs_tail_can_filter_by_command(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    assert cli_main.main(["--output", "json", "capabilities"]) == 0
    capsys.readouterr()
    assert cli_main.main(["whoami", "--json"]) == 0
    capsys.readouterr()

    rc = cli_main.main(["logs", "tail", "--command", "whoami", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["command"] == "whoami"


def test_logs_capture_shell_source(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    inputs = iter(["whoami", "quit"])

    def fake_input(_: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)
    assert cli_main.main(["shell"]) == 0
    capsys.readouterr()

    rc = cli_main.main(["logs", "tail", "--source", "shell", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entries"][0]["command"] == "whoami"
    assert payload["entries"][0]["source"] == "shell"


def test_failed_commands_are_logged_with_nonzero_exit_code(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(["export", "TSLA"])
    capsys.readouterr()

    assert rc == 2
    payload = read_activity(limit=1)[0]
    assert payload["command"] == "export"
    assert payload["ok"] is False
    assert payload["exit_code"] == 2


def test_start_screen_without_command_is_not_logged(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    rc = cli_main.main([])
    capsys.readouterr()

    assert rc == 0
    assert read_activity(limit=5) == []
