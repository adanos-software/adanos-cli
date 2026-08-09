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
    sensitive_value_flags = {
        "--api-key",
        "--api-key-file",
        "--company-name",
        "--email",
        "--name",
        "--output-path",
        "--purpose",
        "--recovery-url",
        "--text",
        "--token",
    }
    ask_value_flags = {"--base-url", "--days", "--from", "--output", "--to"}
    ask_bare_flags = {"--json", "--no-color", "--no-input", "--plain", "--quiet"}
    sanitized: list[str] = []
    redact_next = False
    copy_next_ask_value = False
    in_ask_query = False
    ask_options_ended = False
    ask_query_redacted = False
    redact_later_positional = False
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if redact_next:
            if arg.startswith("-"):
                sanitized.append("<redacted>")
                redact_next = False
                redact_later_positional = True
                idx += 1
                continue
            sanitized.append("<redacted>")
            redact_next = False
            idx += 1
            continue
        if redact_later_positional and not arg.startswith("-"):
            sanitized.append("<redacted>")
            idx += 1
            continue

        flag_name = arg.split("=", 1)[0]
        sensitive_spelling = flag_name in sensitive_value_flags or (
            flag_name.startswith("--")
            and len(flag_name) >= 5
            and any(flag.startswith(flag_name) for flag in sensitive_value_flags)
        )
        if sensitive_spelling and "=" not in arg:
            if in_ask_query:
                copy_next_ask_value = False
            sanitized.append(arg)
            redact_next = True
            idx += 1
            continue
        if sensitive_spelling:
            if in_ask_query:
                copy_next_ask_value = False
            sanitized.append(f"{flag_name}=<redacted>")
            idx += 1
            continue

        if arg == "ask" and not in_ask_query:
            in_ask_query = True
            sanitized.append(arg)
            idx += 1
            continue
        if in_ask_query:
            if ask_options_ended:
                if not ask_query_redacted:
                    sanitized.append("<redacted>")
                    ask_query_redacted = True
                idx += 1
                continue
            if arg == "--":
                ask_options_ended = True
                if not ask_query_redacted:
                    sanitized.append("<redacted>")
                    ask_query_redacted = True
                idx += 1
                continue
            if copy_next_ask_value:
                sanitized.append(arg)
                copy_next_ask_value = False
                idx += 1
                continue
            if arg in ask_value_flags:
                sanitized.append(arg)
                copy_next_ask_value = True
                idx += 1
                continue
            if arg in ask_bare_flags:
                sanitized.append(arg)
                idx += 1
                continue
            if any(arg.startswith(flag + "=") for flag in ask_value_flags):
                sanitized.append(arg)
                idx += 1
                continue
            if not ask_query_redacted:
                sanitized.append("<redacted>")
                ask_query_redacted = True
            idx += 1
            continue

        sanitized.append(arg)
        idx += 1

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
