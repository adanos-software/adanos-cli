"""Interactive shell tests for adanos CLI."""

from __future__ import annotations

import sys
from pathlib import Path


import adanos_cli.config as cli_config
import adanos_cli.main as cli_main


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)
    monkeypatch.setenv("ADANOS_CLI_DISABLE_UPDATE_CHECK", "1")


def test_shell_line_to_argv_behaviors() -> None:
    assert cli_main._shell_line_to_argv("/stock TSLA --days 7") == ["stock", "TSLA", "--days", "7"]
    assert cli_main._shell_line_to_argv("stock TSLA") == ["stock", "TSLA"]
    assert cli_main._shell_line_to_argv("adanos-cli stock TSLA") == ["stock", "TSLA"]
    assert cli_main._shell_line_to_argv("How does TSLA look?") == ["ask", "How does TSLA look?"]
    assert cli_main._shell_line_to_argv("   ") is None


def test_shell_scan_shorthand_normalization() -> None:
    assert cli_main._normalize_shell_argv(["scan"]) == ["scan", "--asset", "stocks", "--style", "starter"]
    assert cli_main._normalize_shell_argv(["scan", "crypto"]) == ["scan", "--asset", "crypto"]
    assert cli_main._normalize_shell_argv(["scan", "stocks", "--style", "daytrader"]) == [
        "scan",
        "--asset",
        "stocks",
        "--style",
        "daytrader",
    ]
    assert cli_main._normalize_shell_argv(["scan", "--style", "daytrader"]) == [
        "scan",
        "--asset",
        "stocks",
        "--style",
        "daytrader",
    ]


def test_shell_fullscreen_resolution(monkeypatch) -> None:
    monkeypatch.delenv("ADANOS_CLI_FULLSCREEN", raising=False)
    assert cli_main._resolve_shell_fullscreen(None) is False

    monkeypatch.setenv("ADANOS_CLI_FULLSCREEN", "1")
    assert cli_main._resolve_shell_fullscreen(None) is True
    assert cli_main._resolve_shell_fullscreen(False) is False
    assert cli_main._resolve_shell_fullscreen(True) is True


def test_format_shell_api_key_status_for_free_with_limit() -> None:
    label = cli_main._format_shell_api_key_status(
        has_api_key=True,
        account_status={
            "account_type": "free",
            "monthly_limit": 250,
            "monthly_remaining": 120,
            "out_of_credits": False,
        },
    )
    assert "free (120/250 left)" in label


def test_format_shell_api_key_status_for_paid_hobby() -> None:
    label = cli_main._format_shell_api_key_status(
        has_api_key=True,
        account_status={
            "account_type": "hobby",
            "paid_active": True,
        },
    )
    assert "hobby (paid)" in label


def test_shell_command_renders_header_and_quits(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    inputs = iter(["quit"])

    def fake_input(_: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)
    rc = cli_main.main(["shell"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Adanos Market Sentiment CLI v" in out
    assert "cwd:" in out
    assert "api:" in out
    assert "Quick Start" in out
    assert "/onboard wizard" in out
    assert "Type /help for full command catalog." in out
    assert "Guided Help" not in out


def test_shell_header_uses_stacked_adanos_brand_mark(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_main, "_supports_color", lambda: False)

    cli_main._print_shell_header("https://api.adanos.org", has_api_key=False)
    out = capsys.readouterr().out

    assert "_____/######\\_____" in out
    assert "\\============================/" in out
    assert "\\----------------------------/" in out
    assert "\\............................/" in out
    assert "\\________________/" not in out
    assert "   / ____ \\" not in out
    assert "\033[" not in out


def test_shell_help_shows_command_catalog(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    inputs = iter(["help", "quit"])

    def fake_input(_: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)
    rc = cli_main.main(["shell"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Guided Help" in out
    assert "/onboard wizard" in out
    assert "/trending --platform" in out
    assert "/stats --platform" in out
    assert "/account" in out


def test_shell_history_and_retry(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    inputs = iter(["whoami", "history", "retry", "quit"])

    def fake_input(_: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)
    rc = cli_main.main(["shell"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Recent commands" in out
    assert "whoami" in out
    assert "Retrying: whoami" in out
    history_path = cli_config.CONFIG_DIR / "shell_history"
    assert history_path.exists()
    assert "whoami" in history_path.read_text(encoding="utf-8")


def test_main_returns_usage_code_for_parse_errors(capsys) -> None:
    rc = cli_main.main(["export", "TSLA"])
    captured = capsys.readouterr()

    assert rc == 2
    assert "the following arguments are required: --kind" in captured.err


def test_shell_stays_open_after_parse_error(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    inputs = iter(["/export TSLA", "quit"])

    def fake_input(_: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)
    rc = cli_main.main(["shell"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "the following arguments are required: --kind" in captured.err
    assert "command_failed: exit code 2 | retry with /retry" in captured.err
    assert "Bye." in captured.out
