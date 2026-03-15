"""CLI configuration and credential handling."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.adanos.org"
SECURE_DIR_MODE = 0o700
SECURE_FILE_MODE = 0o600


def _default_config_dir() -> Path:
    xdg_home = str(os.getenv("XDG_CONFIG_HOME") or "").strip()
    if xdg_home:
        return Path(xdg_home) / "adanos-cli"

    if os.name == "nt":
        appdata = str(os.getenv("APPDATA") or "").strip()
        if appdata:
            return Path(appdata) / "adanos-cli"

    return Path.home() / ".config" / "adanos-cli"


CONFIG_DIR = _default_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"
CREDENTIALS_PATH = CONFIG_DIR / "credentials.json"


@dataclass(frozen=True)
class RuntimeConfig:
    api_key: str
    base_url: str
    api_key_source: str
    base_url_source: str
    profile_name: str | None = None


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _apply_permissions(CONFIG_DIR, SECURE_DIR_MODE)


def _apply_permissions(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # chmod semantics vary across platforms/filesystems. Best effort only.
        return


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    _ensure_config_dir()
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _apply_permissions(path, SECURE_FILE_MODE)


def load_config_file() -> dict[str, Any]:
    return _read_json_file(CONFIG_PATH)


def support_file_path(filename: str) -> Path:
    return CONFIG_DIR / filename


def ensure_config_dir() -> Path:
    _ensure_config_dir()
    return CONFIG_DIR


def apply_secure_permissions(path: Path, *, file_mode: int = SECURE_FILE_MODE) -> None:
    _apply_permissions(path, file_mode)


def load_support_json_file(path: Path) -> dict[str, Any]:
    return _read_json_file(path)


def write_support_json_file(path: Path, payload: dict[str, Any]) -> None:
    _write_json_file(path, payload)


def _normalize_profile_name(name: Any) -> str:
    value = str(name or "").strip()
    return value if value else "default"


def validate_profile_name(name: str) -> str | None:
    value = str(name or "").strip()
    if not value:
        return "Profile name must not be empty."
    if len(value) > 64:
        return "Profile name must be 64 characters or fewer."
    if not all(ch.isalnum() or ch in {"-", "_"} for ch in value):
        return "Profile name must contain only letters, numbers, dashes, and underscores."
    return None


def _normalize_credentials_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "profiles" in payload and isinstance(payload.get("profiles"), dict):
        profiles: dict[str, dict[str, str]] = {}
        for raw_name, raw_entry in payload["profiles"].items():
            profile_name = _normalize_profile_name(raw_name)
            if not isinstance(raw_entry, dict):
                continue
            api_key = str(raw_entry.get("api_key") or "").strip()
            if api_key:
                profiles[profile_name] = {"api_key": api_key}

        active_profile = _normalize_profile_name(payload.get("active_profile"))
        if active_profile not in profiles and profiles:
            active_profile = next(iter(profiles))
        return {
            "active_profile": active_profile,
            "profiles": profiles,
        }

    legacy_key = str(payload.get("api_key") or "").strip()
    if legacy_key:
        return {
            "active_profile": "default",
            "profiles": {"default": {"api_key": legacy_key}},
        }

    return {"active_profile": "default", "profiles": {}}


def load_credentials_file() -> dict[str, Any]:
    payload = _read_json_file(CREDENTIALS_PATH)
    if payload:
        return _normalize_credentials_payload(payload)

    legacy_payload = load_config_file()
    return _normalize_credentials_payload(legacy_payload)


def _write_credentials_payload(payload: dict[str, Any]) -> None:
    _write_json_file(CREDENTIALS_PATH, _normalize_credentials_payload(payload))


def get_active_profile_name() -> str:
    credentials = load_credentials_file()
    active_profile = _normalize_profile_name(credentials.get("active_profile"))
    profiles = credentials.get("profiles") or {}
    if active_profile in profiles:
        return active_profile
    if profiles:
        return next(iter(profiles))
    return "default"


def list_profiles() -> list[dict[str, Any]]:
    credentials = load_credentials_file()
    active_profile = get_active_profile_name()
    profiles = credentials.get("profiles") or {}
    return [
        {
            "name": profile_name,
            "active": profile_name == active_profile,
            "api_key": str((profiles.get(profile_name) or {}).get("api_key") or ""),
        }
        for profile_name in sorted(profiles)
    ]


def set_active_profile(profile_name: str) -> None:
    validation_error = validate_profile_name(profile_name)
    if validation_error:
        raise ValueError(validation_error)

    credentials = load_credentials_file()
    profiles = credentials.get("profiles") or {}
    if profile_name not in profiles:
        raise ValueError(f'Profile "{profile_name}" does not exist.')

    credentials["active_profile"] = profile_name
    _write_credentials_payload(credentials)


def get_profile(profile_name: str | None = None) -> dict[str, Any] | None:
    credentials = load_credentials_file()
    profiles = credentials.get("profiles") or {}
    target_profile = profile_name or get_active_profile_name()
    entry = profiles.get(target_profile)
    if not isinstance(entry, dict):
        return None
    api_key = str(entry.get("api_key") or "").strip()
    if not api_key:
        return None
    return {"name": target_profile, "api_key": api_key}


def delete_profile(profile_name: str | None = None) -> str:
    credentials = load_credentials_file()
    profiles = credentials.get("profiles") or {}
    target_profile = profile_name or get_active_profile_name()
    if target_profile not in profiles:
        raise ValueError(f'Profile "{target_profile}" does not exist.')

    del profiles[target_profile]
    if not profiles:
        if CREDENTIALS_PATH.exists():
            CREDENTIALS_PATH.unlink()
        return target_profile

    active_profile = credentials.get("active_profile")
    if active_profile == target_profile:
        credentials["active_profile"] = next(iter(sorted(profiles)))
    credentials["profiles"] = profiles
    _write_credentials_payload(credentials)
    return target_profile


def save_config_file(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    profile_name: str | None = None,
) -> None:
    settings = load_config_file()
    settings.pop("api_key", None)

    if base_url is not None:
        normalized_base_url = base_url.strip().rstrip("/")
        if normalized_base_url:
            settings["base_url"] = normalized_base_url
        else:
            settings.pop("base_url", None)

    if api_key is not None:
        normalized_api_key = api_key.strip()
        if normalized_api_key:
            target_profile = profile_name or get_active_profile_name()
            validation_error = validate_profile_name(target_profile)
            if validation_error:
                raise ValueError(validation_error)
            credentials = load_credentials_file()
            profiles = dict(credentials.get("profiles") or {})
            profiles[target_profile] = {"api_key": normalized_api_key}
            credentials["profiles"] = profiles
            if not profiles.get(credentials.get("active_profile")):
                credentials["active_profile"] = target_profile
            if profile_name:
                credentials["active_profile"] = target_profile
            _write_credentials_payload(credentials)
        elif profile_name:
            delete_profile(profile_name)
        elif CREDENTIALS_PATH.exists():
            CREDENTIALS_PATH.unlink()

    # Keep a plain config file around even when only credentials changed so path discovery
    # and tooling remain stable.
    _write_json_file(CONFIG_PATH, settings)


def clear_config_file() -> None:
    for path in (CONFIG_PATH, CREDENTIALS_PATH):
        if path.exists():
            path.unlink()


def resolve_runtime_config(
    *, api_key_override: str | None = None, base_url_override: str | None = None
) -> RuntimeConfig:
    settings = load_config_file()
    credentials = load_credentials_file()
    active_profile = get_active_profile_name()

    api_key = (api_key_override or "").strip()
    api_key_source = "flag" if api_key else "missing"
    profile_name: str | None = None
    if not api_key:
        env_api_key = str(os.getenv("ADANOS_API_KEY") or "").strip()
        if env_api_key:
            api_key = env_api_key
            api_key_source = "env"
        else:
            credentials_profiles = credentials.get("profiles") or {}
            selected_profile = credentials_profiles.get(active_profile) or {}
            credentials_api_key = str(selected_profile.get("api_key") or "").strip()
            if credentials_api_key:
                api_key = credentials_api_key
                api_key_source = "credentials"
                profile_name = active_profile
            else:
                legacy_api_key = str(settings.get("api_key") or "").strip()
                if legacy_api_key:
                    api_key = legacy_api_key
                    api_key_source = "config_legacy"
                    profile_name = "default"
    else:
        profile_name = active_profile if load_credentials_file().get("profiles") else None

    base_url = (base_url_override or "").strip()
    base_url_source = "flag" if base_url else "default"
    if not base_url:
        env_base_url = str(os.getenv("ADANOS_BASE_URL") or "").strip()
        if env_base_url:
            base_url = env_base_url
            base_url_source = "env"
        else:
            config_base_url = str(settings.get("base_url") or "").strip()
            if config_base_url:
                base_url = config_base_url
                base_url_source = "config"
            else:
                base_url = DEFAULT_BASE_URL

    return RuntimeConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        api_key_source=api_key_source,
        base_url_source=base_url_source,
        profile_name=profile_name,
    )


def masked_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if len(key) < 10:
        return "(not set)"
    return f"{key[:10]}...{key[-4:]}"
