"""Diagnostics, config security, and runtime mode tests for the adanos CLI."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import httpx
import respx


import adanos_cli.config as cli_config
import adanos_cli.main as cli_main


def _isolate_config(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)
    return cfg_dir, cfg_path, credentials_path


def test_config_set_splits_settings_and_credentials(tmp_path, monkeypatch, capsys) -> None:
    cfg_dir, cfg_path, credentials_path = _isolate_config(tmp_path, monkeypatch)

    rc = cli_main.main(
        [
            "--output",
            "json",
            "config",
            "set",
            "--api-key",
            "adanos_key_abcdefghijklmnopqrstuvwxyz123456",
            "--base-url",
            "https://example.com/",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["config_path"] == str(cfg_path)
    assert payload["credentials_path"] == str(credentials_path)

    config_data = json.loads(cfg_path.read_text(encoding="utf-8"))
    credentials_data = json.loads(credentials_path.read_text(encoding="utf-8"))

    assert config_data == {"base_url": "https://example.com"}
    assert credentials_data == {
        "active_profile": "default",
        "profiles": {
            "default": {
                "api_key": "adanos_key_abcdefghijklmnopqrstuvwxyz123456",
            }
        },
    }

    if os.name != "nt":
        assert stat.S_IMODE(cfg_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600


@respx.mock
def test_whoami_json_reports_runtime_sources(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv("ADANOS_BASE_URL", "https://api.adanos.org")

    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 42},
            headers={
                "X-Account-Type": "hobby",
                "X-RateLimit-Limit-Monthly": "250000",
                "X-RateLimit-Remaining-Monthly": "249983",
                "X-RateLimit-Used-Monthly": "17",
                "X-RateLimit-Reset-Monthly": "2026-07-23T10:00:00Z",
            },
        )
    )

    rc = cli_main.main(["whoami", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "whoami"
    assert payload["api_key_source"] == "env"
    assert payload["base_url_source"] == "env"
    assert payload["profile"] is None
    assert payload["account_type"] == "hobby"
    assert payload["status"] == "paid_active"


def test_doctor_json_fails_without_key(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)

    rc = cli_main.main(["doctor", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "doctor"
    assert payload["ok"] is False
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["Credentials"]["status"] == "fail"
    assert checks["Credentials"]["next_step"] == "Run: adanos login --api-key sk_live_xxx"
    assert checks["API Validation"]["status"] == "fail"
    assert checks["API Validation"]["detail"] == "Skipped because credentials are not configured."


@respx.mock
def test_doctor_text_is_compact_when_healthy(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv("ADANOS_BASE_URL", "https://api.adanos.org")

    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 42},
            headers={
                "X-Account-Type": "professional",
                "X-RateLimit-Limit-Monthly": "2500000",
                "X-RateLimit-Remaining-Monthly": "2499983",
                "X-RateLimit-Used-Monthly": "17",
                "X-RateLimit-Reset-Monthly": "2026-07-23T10:00:00Z",
            },
        )
    )

    rc = cli_main.main(["doctor"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "No issues found. Valid key (professional)" in out
    assert "CLI Version" not in out
    assert "Credentials:" not in out
    assert "Use `adanos whoami` for active identity details." in out


@respx.mock
def test_doctor_verbose_shows_pass_checks(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv("ADANOS_BASE_URL", "https://api.adanos.org")

    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 42},
            headers={
                "X-Account-Type": "professional",
                "X-RateLimit-Limit-Monthly": "2500000",
                "X-RateLimit-Remaining-Monthly": "2499983",
                "X-RateLimit-Used-Monthly": "17",
                "X-RateLimit-Reset-Monthly": "2026-07-23T10:00:00Z",
            },
        )
    )

    rc = cli_main.main(["doctor", "--verbose"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "CLI Version" in out
    assert "Credentials:" in out
    assert "API Validation: Valid key (professional)" in out


@respx.mock
def test_doctor_text_shows_warns_and_hides_pass_checks(tmp_path, monkeypatch, capsys) -> None:
    _, _, credentials_path = _isolate_config(tmp_path, monkeypatch)
    cli_config.save_config_file(
        api_key="adanos_key_abcdefghijklmnopqrstuvwxyz123456",
        base_url="https://api.adanos.org",
    )
    if os.name != "nt":
        credentials_path.chmod(0o644)

    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 42},
            headers={
                "X-Account-Type": "professional",
                "X-RateLimit-Limit-Monthly": "2500000",
                "X-RateLimit-Remaining-Monthly": "2499983",
                "X-RateLimit-Used-Monthly": "17",
                "X-RateLimit-Reset-Monthly": "2026-07-23T10:00:00Z",
            },
        )
    )

    rc = cli_main.main(["doctor"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Credentials File Permissions" in out
    assert "Use --verbose for the full list." in out
    assert "CLI Version" not in out
    assert "API Validation: Valid key (professional)" not in out


def test_quiet_implies_json_output(capsys) -> None:
    rc = cli_main.main(["--quiet", "capabilities"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "adanos-cli"


def test_main_auto_json_for_real_cli_invocation(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["adanos", "capabilities"])
    rc = cli_main.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "adanos-cli"
