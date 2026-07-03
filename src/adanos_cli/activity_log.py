"""Local CLI activity logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config as cli_config


def activity_log_path() -> Path:
    return cli_config.support_file_path("activity.log")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_argv(argv: list[str]) -> list[str]:
    sanitized: list[str] = []
    redact_next = False
    for token in argv:
        if redact_next:
            sanitized.append("<redacted>")
            redact_next = False
            continue
        if token in {"--api-key", "--api-key-file"}:
            sanitized.append(token)
            redact_next = True
            continue
        if token.startswith("--api-key="):
            sanitized.append("--api-key=<redacted>")
            continue
        if token.startswith("--api-key-file="):
            sanitized.append("--api-key-file=<redacted>")
            continue
        sanitized.append(token)

    if redact_next:
        sanitized.append("<redacted>")
    return sanitized


def _command_name(argv: list[str]) -> str | None:
    value_flags = {"--api-key", "--api-key-file", "--base-url", "--output"}
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token in value_flags:
            skip_next = True
            continue
        if any(token.startswith(prefix + "=") for prefix in value_flags):
            continue
        if token.startswith("-"):
            continue
        return token
    return None


def append_activity(argv: list[str], *, source: str, exit_code: int, duration_ms: int) -> None:
    path = activity_log_path()
    cli_config.ensure_config_dir()
    entry = {
        "captured_at": _utc_now(),
        "source": source,
        "command": _command_name(argv),
        "argv": sanitize_argv(argv),
        "exit_code": exit_code,
        "ok": exit_code == 0,
        "duration_ms": max(0, int(duration_ms)),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    cli_config.apply_secure_permissions(path)


def read_activity(*, limit: int = 20, command: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
    path = activity_log_path()
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if command and payload.get("command") != command:
            continue
        if source and payload.get("source") != source:
            continue
        entries.append(payload)

    entries.reverse()
    return entries[: max(1, limit)]
