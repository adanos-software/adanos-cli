"""Onboarding flow tests for the adanos CLI."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import respx


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


def test_welcome_screen_without_key(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)
    rc = cli_main.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ADANOS CLI" in out
    assert "API key: not configured" in out
    assert "create a key on https://adanos.com/account, then run: adanos login" in out


def test_welcome_screen_with_key(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_example_key_1234567890")
    rc = cli_main.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ADANOS CLI" in out
    assert "API key: configured" in out
    assert "Quick start:" in out


def test_start_screen_in_tty_keeps_header_but_does_not_enter_shell(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_example_key_1234567890")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    def _unexpected_input(*_args, **_kwargs):
        raise AssertionError("shell should not start automatically")

    monkeypatch.setattr("builtins.input", _unexpected_input)

    rc = cli_main.main([])
    out = capsys.readouterr().out

    assert rc == 0
    assert "ADANOS  Market Sentiment CLI v" in out
    assert "Start Here" in out
    assert "adanos shell" in out
    assert "adanos consensus TSLA" in out


def test_onboard_guide_points_to_adanos_com(capsys) -> None:
    rc = cli_main.main(["--output", "text", "onboard"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1) Sign up at https://adanos.com/register (email code, Google or Apple)." in out
    assert "2) Create an API key on https://adanos.com/account." in out
    assert "adanos login  # paste the key at the hidden prompt" in out
    assert "Lost your key? Log in at https://adanos.com/login and rotate it on https://adanos.com/account." in out
    assert "redeem" not in out


def test_onboard_guide_json_lists_adanos_com_steps(capsys) -> None:
    rc = cli_main.main(["--json", "onboard", "guide"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["kind"] == "onboarding_guide"
    assert payload["onboarding"]["register_url"] == "https://adanos.com/register"
    assert payload["onboarding"]["login_url"] == "https://adanos.com/login"
    assert payload["onboarding"]["account_url"] == "https://adanos.com/account"
    assert payload["onboarding"]["steps"] == [
        "Sign up or log in at https://adanos.com/register",
        "Create an API key on https://adanos.com/account",
        "adanos login  # paste the key at the hidden prompt",
    ]


def test_onboard_guide_mentions_existing_key_when_available(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_example_key_1234567890")
    rc = cli_main.main(["onboard"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "API key is already configured." in out


def test_onboard_wizard_not_available_in_json_mode(capsys) -> None:
    rc = cli_main.main(["--output", "json", "onboard", "wizard"])
    captured = capsys.readouterr()
    assert rc == 2
    payload = json.loads(captured.err)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "onboard_wizard_unsupported"


def test_onboard_wizard_respects_no_input(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_main, "is_interactive", lambda: True)

    def _unexpected_input(*_args, **_kwargs):
        raise AssertionError("wizard should not prompt with --no-input")

    monkeypatch.setattr("builtins.input", _unexpected_input)

    rc = cli_main.main(["--no-input", "onboard", "wizard"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Interactive wizard is disabled by --no-input" in captured.err


def test_onboard_wizard_sends_user_to_adanos_com_and_stores_pasted_key(isolated_config, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_main, "is_interactive", lambda: True)

    def _unexpected_input(*_args, **_kwargs):
        raise AssertionError("wizard without a stored key should only ask for the key")

    monkeypatch.setattr("builtins.input", _unexpected_input)
    monkeypatch.setattr(cli_main, "getpass", lambda prompt="": "adanos_key_pastedabcdefghijklmnopqrstuvwxyz123456")

    rc = cli_main.main(["--output", "text", "onboard", "wizard"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "1) Sign up or log in at https://adanos.com/register" in out
    assert "2) Create an API key on https://adanos.com/account" in out
    assert "API key stored." in out
    assert cli_config.get_profile("default")["api_key"] == "adanos_key_pastedabcdefghijklmnopqrstuvwxyz123456"


@respx.mock
def test_onboard_register_prints_signup_url_without_api_call(capsys) -> None:
    rc = cli_main.main(["--output", "text", "onboard", "register"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == (
        "Create your account and API key on adanos.com (email code, Google or Apple).\n"
        "1) Sign up or log in at https://adanos.com/register\n"
        "2) Create an API key on https://adanos.com/account\n"
        "3) adanos login  # paste the key at the hidden prompt\n"
    )


@respx.mock
def test_onboard_register_json_accepts_legacy_flags(capsys) -> None:
    rc = cli_main.main(
        ["--json", "onboard", "register", "--name", "Alex", "--email", "alex@example.com", "--purpose", "CLI"]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "url": "https://adanos.com/register",
        "steps": [
            "Sign up or log in at https://adanos.com/register",
            "Create an API key on https://adanos.com/account",
            "adanos login  # paste the key at the hidden prompt",
        ],
        "kind": "onboard_registration",
        "command": "onboard",
        "subcommand": "register",
    }


@respx.mock
def test_onboard_recover_json_points_to_login_without_request(capsys) -> None:
    rc = cli_main.main(["--json", "onboard", "recover", "--email", "alex@example.com"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "url": "https://adanos.com/login",
        "steps": [
            "Log in at https://adanos.com/login",
            "Rotate the API key on https://adanos.com/account",
            "adanos login  # paste the key at the hidden prompt",
        ],
        "kind": "onboard_recovery",
        "command": "onboard",
        "subcommand": "recover",
    }


@respx.mock
def test_onboard_redeem_is_a_stub_that_fails_without_reading_stdin(monkeypatch, capsys) -> None:
    stdin = io.StringIO("kt_private\n")
    monkeypatch.setattr(sys, "stdin", stdin)

    rc = cli_main.main(["--json", "onboard", "redeem", "--token-stdin", "--save"])
    captured = capsys.readouterr()

    assert rc == 2
    assert captured.out == ""
    assert stdin.read() == "kt_private\n"
    assert json.loads(captured.err) == {
        "ok": False,
        "error": {
            "code": "onboard_redeem_removed",
            "message": "One-time token redemption was removed. API keys are now created on adanos.com.",
            "hint": "Create or rotate your key on https://adanos.com/account, then run `adanos login`.",
        },
    }
