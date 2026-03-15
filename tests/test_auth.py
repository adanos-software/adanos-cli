"""Auth profile management tests for the adanos CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path


import adanos_cli.config as cli_config
import adanos_cli.main as cli_main


def _isolate_config(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)
    return cfg_path, credentials_path


def test_auth_profile_flow(tmp_path, monkeypatch, capsys) -> None:
    cfg_path, credentials_path = _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(
        [
            "--output",
            "json",
            "auth",
            "login",
            "--api-key",
            "adanos_key_firstprofileabcdefghijklmnopqrstuvwxyz",
            "--profile",
            "prod",
            "--base-url",
            "https://example.com/",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "prod"

    rc = cli_main.main(
        [
            "--output",
            "json",
            "auth",
            "login",
            "--api-key",
            "adanos_key_secondprofileabcdefghijklmnopqrstuvwxyz",
            "--profile",
            "staging",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "staging"

    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert credentials["active_profile"] == "staging"
    assert sorted(credentials["profiles"]) == ["prod", "staging"]

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["base_url"] == "https://example.com"

    rc = cli_main.main(["auth", "switch", "prod", "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "prod"

    rc = cli_main.main(["auth", "current", "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "prod"
    assert payload["api_key"] == "adanos_key...wxyz"

    rc = cli_main.main(["config", "show", "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_profile"] == "prod"
    assert len(payload["profiles"]) == 2

    rc = cli_main.main(["auth", "logout", "--profile", "staging", "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "staging"

    rc = cli_main.main(["auth", "list", "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["name"] for item in payload["profiles"]] == ["prod"]
    assert payload["active_profile"] == "prod"


def test_auth_login_keeps_local_api_key_flag_attached(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(
        [
            "auth",
            "login",
            "--api-key",
            "adanos_key_profileflagabcdefghijklmnopqrstuvwxyz",
            "--profile",
            "sandbox",
            "--output",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "sandbox"

    rc = cli_main.main(["whoami", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "sandbox"
    assert payload["api_key_source"] == "credentials"


def test_auth_subcommands_accept_json_shortcut(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(
        [
            "auth",
            "login",
            "--api-key",
            "adanos_key_profilejsonabcdefghijklmnopqrstuvwxyz",
            "--profile",
            "prod",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_login"
    assert payload["kind"] == "auth_login"
    assert payload["command"] == "auth"
    assert payload["subcommand"] == "login"
    assert payload["profile"] == "prod"

    rc = cli_main.main(["auth", "current", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_current"
    assert payload["kind"] == "auth_profile"
    assert payload["command"] == "auth"
    assert payload["subcommand"] == "current"
    assert payload["profile"] == "prod"

    rc = cli_main.main(["auth", "list", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_list"
    assert payload["kind"] == "auth_profile_list"
    assert payload["command"] == "auth"
    assert payload["subcommand"] == "list"
    assert payload["active_profile"] == "prod"
    assert payload["profiles"][0]["name"] == "prod"

    rc = cli_main.main(["auth", "switch", "prod", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_switch"
    assert payload["kind"] == "auth_switch"
    assert payload["command"] == "auth"
    assert payload["subcommand"] == "switch"
    assert payload["profile"] == "prod"

    rc = cli_main.main(["auth", "logout", "--profile", "prod", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_logout"
    assert payload["kind"] == "auth_logout"
    assert payload["command"] == "auth"
    assert payload["subcommand"] == "logout"
    assert payload["profile"] == "prod"


def test_config_subcommands_accept_json_shortcut(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(
        [
            "config",
            "set",
            "--api-key",
            "adanos_key_configjsonabcdefghijklmnopqrstuvwxyz",
            "--base-url",
            "https://example.com",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "config_set"
    assert payload["kind"] == "config_set"
    assert payload["command"] == "config"
    assert payload["subcommand"] == "set"

    rc = cli_main.main(["config", "show", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "config_show"
    assert payload["kind"] == "config_show"
    assert payload["command"] == "config"
    assert payload["subcommand"] == "show"
    assert payload["base_url"] == "https://example.com"

    rc = cli_main.main(["config", "clear", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "config_clear"
    assert payload["kind"] == "config_clear"
    assert payload["command"] == "config"
    assert payload["subcommand"] == "clear"


def test_login_alias_works(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(
        [
            "login",
            "--api-key",
            "adanos_key_aliasprofileabcdefghijklmnopqrstuvwxyz",
            "--profile",
            "prod",
            "--output",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_login"
    assert payload["profile"] == "prod"

    rc = cli_main.main(["logout", "--profile", "prod", "--output", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_logout"
    assert payload["profile"] == "prod"


def test_auth_login_prompts_secret_in_interactive_mode(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr("adanos_cli.commands.auth.is_interactive", lambda: True)
    monkeypatch.setattr(
        "adanos_cli.commands.auth.getpass",
        lambda prompt="": "adanos_key_promptedabcdefghijklmnopqrstuvwxyz123456",
    )

    rc = cli_main.main(["auth", "login", "--profile", "prod", "--output", "json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "auth_login"
    assert payload["profile"] == "prod"
    credentials = json.loads(cli_config.CREDENTIALS_PATH.read_text(encoding="utf-8"))
    assert credentials["profiles"]["prod"]["api_key"] == "adanos_key_promptedabcdefghijklmnopqrstuvwxyz123456"
