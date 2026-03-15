"""Update notifier tests for the adanos CLI."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


import adanos_cli.config as cli_config
import adanos_cli.main as cli_main
from adanos_cli.update_notifier import format_update_notice, get_update_payload, is_newer_version


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)


def test_is_newer_version_semver() -> None:
    assert is_newer_version("1.21.0", "1.20.0") is True
    assert is_newer_version("1.20.0", "1.20.0") is False
    assert is_newer_version("1.19.9", "1.20.0") is False


def test_is_newer_version_rejects_invalid_versions() -> None:
    assert is_newer_version("1.21", "1.20.0") is False
    assert is_newer_version("latest", "1.20.0") is False
    assert is_newer_version("1.21.0", "current") is False


def test_get_update_payload_returns_none_when_current(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    payload = get_update_payload("1.20.0", fetch_latest_version=lambda **_: "1.20.0")
    assert payload is None


def test_get_update_payload_returns_none_when_fetcher_returns_empty(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    payload = get_update_payload("1.20.0", fetch_latest_version=lambda **_: None)
    assert payload is None


def test_get_update_payload_returns_payload_and_uses_cache(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    now = datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc)
    payload = get_update_payload("1.20.0", now=now, fetch_latest_version=lambda **_: "1.21.0")
    assert payload is not None
    assert payload["latest_version"] == "1.21.0"

    reused = get_update_payload(
        "1.20.0",
        now=now,
        fetch_latest_version=lambda **_: (_ for _ in ()).throw(AssertionError("cache should be used")),
    )
    assert reused is not None
    assert reused["latest_version"] == "1.21.0"


def test_get_update_payload_refetches_when_cache_is_stale(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    cli_config.write_support_json_file(
        cli_config.support_file_path("update-check.json"),
        {"checked_at": "2026-03-10T08:00:00Z", "latest_version": "1.21.0"},
    )
    calls: list[float] = []

    payload = get_update_payload(
        "1.20.0",
        now=datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc),
        fetch_latest_version=lambda **kwargs: calls.append(kwargs["timeout_s"]) or "1.22.0",
    )

    assert calls == [0.6]
    assert payload is not None
    assert payload["latest_version"] == "1.22.0"


def test_get_update_payload_uses_stale_cached_newer_version_when_fetch_fails(tmp_path, monkeypatch) -> None:
    _isolate_config(tmp_path, monkeypatch)
    cli_config.write_support_json_file(
        cli_config.support_file_path("update-check.json"),
        {"checked_at": "2026-03-10T08:00:00Z", "latest_version": "1.21.0"},
    )

    payload = get_update_payload(
        "1.20.0",
        now=datetime(2026, 3, 15, 8, 0, tzinfo=timezone.utc),
        fetch_latest_version=lambda **_: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert payload is not None
    assert payload["latest_version"] == "1.21.0"


def test_format_update_notice() -> None:
    notice = format_update_notice(
        {
            "current_version": "1.20.0",
            "latest_version": "1.21.0",
            "upgrade_hint": "pipx upgrade adanos-cli",
        }
    )
    assert "1.21.0" in notice
    assert "pipx upgrade adanos-cli" in notice


def test_start_screen_skips_update_check_when_disabled(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("ADANOS_CLI_DISABLE_UPDATE_CHECK", "1")
    monkeypatch.setattr(cli_main, "get_update_payload", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not fetch")))

    rc = cli_main.main([])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Update available:" not in out


def test_start_screen_prints_update_notice(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        cli_main,
        "get_update_payload",
        lambda *_args, **_kwargs: {
            "current_version": "1.20.0",
            "latest_version": "1.21.0",
            "upgrade_hint": "pipx upgrade adanos-cli",
        },
    )

    rc = cli_main.main([])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Update available: adanos-cli 1.21.0" in out
