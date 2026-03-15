"""Config/runtime helper tests for the adanos CLI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


import adanos_cli.config as cli_config


def _isolate_config(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)
    return cfg_path, credentials_path


def test_support_file_helpers_round_trip(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    path = cli_config.support_file_path("custom.json")
    cli_config.write_support_json_file(path, {"ok": True})
    assert cli_config.load_support_json_file(path) == {"ok": True}


def test_load_support_json_file_returns_empty_for_missing_file(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    assert cli_config.load_support_json_file(cli_config.support_file_path("missing.json")) == {}


def test_write_support_json_file_creates_config_directory(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    path = cli_config.support_file_path("nested.json")
    cli_config.write_support_json_file(path, {"ok": True})

    assert path.exists()
    assert cli_config.CONFIG_DIR.exists()


def test_apply_secure_permissions_is_best_effort(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    target = tmp_path / "sample.txt"
    target.write_text("ok", encoding="utf-8")
    cli_config.apply_secure_permissions(target)

    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == cli_config.SECURE_FILE_MODE


def test_resolve_runtime_config_prefers_flag_over_env_and_credentials(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    cli_config.save_config_file(api_key="adanos_key_credentialsabcdefghijklmnopqrstuvwxyz", base_url="https://stored.example")
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_envabcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("ADANOS_BASE_URL", "https://env.example")

    runtime = cli_config.resolve_runtime_config(
        api_key_override="adanos_key_flagabcdefghijklmnopqrstuvwxyz",
        base_url_override="https://flag.example",
    )

    assert runtime.api_key_source == "flag"
    assert runtime.base_url_source == "flag"
    assert runtime.api_key == "adanos_key_flagabcdefghijklmnopqrstuvwxyz"
    assert runtime.base_url == "https://flag.example"


def test_resolve_runtime_config_uses_env_when_flags_absent(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_envabcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("ADANOS_BASE_URL", "https://env.example")

    runtime = cli_config.resolve_runtime_config()

    assert runtime.api_key_source == "env"
    assert runtime.base_url_source == "env"
    assert runtime.api_key == "adanos_key_envabcdefghijklmnopqrstuvwxyz"
    assert runtime.base_url == "https://env.example"


def test_resolve_runtime_config_uses_active_profile_when_no_flag_or_env(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    cli_config.save_config_file(api_key="adanos_key_defaultabcdefghijklmnopqrstuvwxyz", profile_name="default")
    cli_config.save_config_file(api_key="adanos_key_prodabcdefghijklmnopqrstuvwxyz", profile_name="prod")
    cli_config.set_active_profile("prod")
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)

    runtime = cli_config.resolve_runtime_config()

    assert runtime.api_key_source == "credentials"
    assert runtime.profile_name == "prod"
    assert runtime.api_key == "adanos_key_prodabcdefghijklmnopqrstuvwxyz"


def test_resolve_runtime_config_uses_config_base_url_as_fallback(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    cli_config.save_config_file(base_url="https://stored.example")
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)

    runtime = cli_config.resolve_runtime_config()

    assert runtime.base_url_source == "config"
    assert runtime.base_url == "https://stored.example"


def test_save_config_file_keeps_plain_config_stable(tmp_path, monkeypatch) -> None:
    cfg_path, credentials_path = _isolate_config(tmp_path, monkeypatch)

    cli_config.save_config_file(
        api_key="adanos_key_credentialsabcdefghijklmnopqrstuvwxyz",
        base_url="https://api.adanos.org/",
    )

    assert json.loads(cfg_path.read_text(encoding="utf-8")) == {"base_url": "https://api.adanos.org"}
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    assert credentials["profiles"]["default"]["api_key"] == "adanos_key_credentialsabcdefghijklmnopqrstuvwxyz"


def test_save_config_file_writes_to_named_profile(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)

    cli_config.save_config_file(
        api_key="adanos_key_prodabcdefghijklmnopqrstuvwxyz",
        profile_name="prod",
    )

    profile = cli_config.get_profile("prod")
    assert profile is not None
    assert profile["api_key"] == "adanos_key_prodabcdefghijklmnopqrstuvwxyz"
