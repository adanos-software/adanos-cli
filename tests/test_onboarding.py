"""Onboarding flow tests for the adanos CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
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
    assert "adanos onboard register" in out


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
    assert "Adanos Market Sentiment CLI v" in out
    assert "Start Here" in out
    assert "adanos shell" in out
    assert "adanos consensus TSLA" in out


def test_onboard_guide_is_cli_first(capsys) -> None:
    rc = cli_main.main(["onboard"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Guided setup (no curl):" in out
    assert "adanos login --api-key sk_live_xxx" in out
    assert "adanos onboard wizard" in out
    assert "adanos onboard register" in out
    assert "adanos onboard recover" in out
    assert "curl -s" not in out


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


def test_onboard_wizard_accepts_existing_key(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "is_interactive", lambda: True)

    answers = iter(["y"])

    def fake_input(prompt: str = "") -> str:
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(
        cli_main,
        "getpass",
        lambda prompt="": "adanos_key_existingabcdefghijklmnopqrstuvwxyz123456",
    )

    rc = cli_main.main(["onboard", "wizard"])
    assert rc == 0

    credentials = json.loads(cli_config.CREDENTIALS_PATH.read_text(encoding="utf-8"))
    assert credentials["active_profile"] == "default"
    assert credentials["profiles"]["default"]["api_key"] == "adanos_key_existingabcdefghijklmnopqrstuvwxyz123456"


@respx.mock
def test_onboard_register_accepts_email_verification_flow(capsys) -> None:
    respx.post("https://api.adanos.org/auth/v1/register").mock(
        return_value=httpx.Response(
            202,
            json={
                "success": True,
                "action": "accepted",
                "message": "If your request is valid, check your email for a one-time link to retrieve your API key.",
                "email": "alex@example.com",
            },
        )
    )

    rc = cli_main.main(
        [
            "onboard",
            "register",
            "--name",
            "Alex Schneider",
            "--email",
            "alex@example.com",
            "--purpose",
            "CLI usage for stocks and crypto",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Registration accepted." in out
    assert "check your email" in out.lower()
    assert "adanos onboard redeem --token <delivery_token> --save" in out


@respx.mock
def test_onboard_recover_requests_email_confirmation(capsys) -> None:
    respx.post("https://adanos.org/api/recover").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "action": "accepted",
                "message": "If an active account exists for this email, further recovery instructions will be sent separately.",
            },
        )
    )

    rc = cli_main.main(["onboard", "recover", "--email", "alex@example.com"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Recovery request accepted." in out
    assert "Check your email for the secure recovery link." in out


@respx.mock
def test_onboard_recover_json_outputs_structured_response(capsys) -> None:
    respx.post("https://adanos.org/api/recover").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "action": "accepted",
                "message": "If an active account exists for this email, further recovery instructions will be sent separately.",
            },
        )
    )

    rc = cli_main.main(["--output", "json", "onboard", "recover", "--email", "alex@example.com", "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["kind"] == "onboard_recovery"
    assert payload["success"] is True
    assert payload["action"] == "accepted"


@respx.mock
def test_onboard_redeem_save_writes_config(tmp_path, monkeypatch) -> None:
    token = "kt_a8Kj2mNpQrStUvWxYz1234567890AbCdEfGhIjKlMnO"
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"

    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)

    respx.post("https://api.adanos.org/auth/v1/key/redeem", json={"token": token}).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "api_key": "adanos_key_abcdefghijklmnopqrstuvwxyz123456",
                "plan": "free",
                "email": "al***@example.com",
                "retrieved_at": "2026-02-05T15:45:00Z",
            },
        )
    )

    rc = cli_main.main(["onboard", "redeem", "--token", token, "--save"])
    assert rc == 0
    assert cfg_path.exists()
    assert credentials_path.exists()

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["base_url"] == "https://api.adanos.org"
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert credentials["active_profile"] == "default"
    assert credentials["profiles"]["default"]["api_key"] == "adanos_key_abcdefghijklmnopqrstuvwxyz123456"


@respx.mock
def test_onboard_wizard_stops_after_register_until_email_arrives(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "is_interactive", lambda: True)
    respx.post("https://api.adanos.org/auth/v1/register").mock(
        return_value=httpx.Response(
            202,
            json={
                "success": True,
                "action": "accepted",
                "message": "If your request is valid, check your email for a one-time link to retrieve your API key.",
                "email": "alex@example.com",
            },
        )
    )

    answers = iter([
        "n",
        "Alex Example",
        "alex@example.com",
        "CLI usage for stocks and crypto",
        "",
        "n",
    ])

    def fake_input(prompt: str = "") -> str:
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    rc = cli_main.main(["onboard", "wizard"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Registration accepted." in out
    assert "Check your email for the secure verification link." in out
    assert "adanos onboard redeem --token <delivery_token> --save" in out
