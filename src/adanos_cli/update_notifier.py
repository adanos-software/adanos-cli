"""PyPI-backed update check with local caching."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from . import config as cli_config


PYPI_PROJECT = "adanos-cli"
PYPI_URL = f"https://pypi.org/pypi/{PYPI_PROJECT}/json"
UPDATE_CACHE_TTL_HOURS = 24


def update_cache_path():
    return cli_config.support_file_path("update-check.json")


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    parts = [part.strip() for part in str(value or "").split(".")]
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def is_newer_version(latest: str, current: str) -> bool:
    latest_version = _parse_semver(latest)
    current_version = _parse_semver(current)
    if latest_version is None or current_version is None:
        return False
    return latest_version > current_version


def _parse_checked_at(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cache_is_fresh(payload: dict[str, Any], *, now: datetime) -> bool:
    checked_at = _parse_checked_at(str(payload.get("checked_at") or ""))
    if checked_at is None:
        return False
    return checked_at >= now - timedelta(hours=UPDATE_CACHE_TTL_HOURS)


def _read_cache() -> dict[str, Any]:
    return cli_config.load_support_json_file(update_cache_path())


def _write_cache(latest_version: str, *, now: datetime) -> None:
    cli_config.write_support_json_file(
        update_cache_path(),
        {
            "checked_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "latest_version": latest_version,
        },
    )


def _fetch_latest_version(*, timeout_s: float) -> str | None:
    response = httpx.get(
        PYPI_URL,
        timeout=timeout_s,
        headers={"User-Agent": f"{PYPI_PROJECT}-notifier"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    latest = str(info.get("version") or "").strip()
    return latest or None


def get_update_payload(
    current_version: str,
    *,
    now: datetime | None = None,
    timeout_s: float = 0.6,
    fetch_latest_version: Callable[..., str | None] | None = None,
) -> dict[str, str] | None:
    current_time = now or datetime.now(timezone.utc)
    cache = _read_cache()
    cached_latest = str(cache.get("latest_version") or "").strip()
    if cached_latest and _cache_is_fresh(cache, now=current_time):
        if is_newer_version(cached_latest, current_version):
            return {
                "current_version": current_version,
                "latest_version": cached_latest,
                "upgrade_hint": "pipx upgrade adanos-cli",
            }
        return None

    fetcher = fetch_latest_version or _fetch_latest_version
    try:
        latest = fetcher(timeout_s=timeout_s)
    except Exception:
        if cached_latest and is_newer_version(cached_latest, current_version):
            return {
                "current_version": current_version,
                "latest_version": cached_latest,
                "upgrade_hint": "pipx upgrade adanos-cli",
            }
        return None

    if not latest:
        return None

    _write_cache(latest, now=current_time)
    if not is_newer_version(latest, current_version):
        return None

    return {
        "current_version": current_version,
        "latest_version": latest,
        "upgrade_hint": "pipx upgrade adanos-cli",
    }


def format_update_notice(payload: dict[str, str]) -> str:
    return (
        f"Update available: adanos-cli {payload['latest_version']} "
        f"(current {payload['current_version']}). "
        f"Run `{payload['upgrade_hint']}`."
    )
