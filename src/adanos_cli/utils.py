"""Utility helpers for CLI output and conversions."""

from __future__ import annotations

import json
import sys
from typing import Any


class CliUsageError(ValueError):
    """Raised when command arguments are invalid."""


class CliRuntimeError(RuntimeError):
    """Raised when remote API calls fail in a user-facing flow."""


def to_plain(value: Any) -> Any:
    """Convert generated model objects recursively into plain Python objects."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    if isinstance(value, tuple):
        return [to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_plain(to_dict())

    as_dict = getattr(value, "__dict__", None)
    if isinstance(as_dict, dict):
        filtered = {k: v for k, v in as_dict.items() if not k.startswith("_")}
        if filtered:
            return to_plain(filtered)

    return str(value)


def print_json(data: Any, *, file=None) -> None:
    target = file if file is not None else sys.stdout
    print(json.dumps(to_plain(data), indent=2, ensure_ascii=False, sort_keys=True), file=target)


def with_json_metadata(
    data: Any,
    *,
    kind: str | None = None,
    command: str | None = None,
    subcommand: str | None = None,
    **defaults: Any,
) -> Any:
    payload = to_plain(data)
    if not isinstance(payload, dict):
        return payload
    if kind is not None:
        payload.setdefault("kind", kind)
    if command is not None:
        payload.setdefault("command", command)
    if subcommand is not None:
        payload.setdefault("subcommand", subcommand)
    for key, value in defaults.items():
        if value is None:
            continue
        payload.setdefault(key, to_plain(value))
    return payload


def print_err(message: str) -> None:
    print(message, file=sys.stderr)


def short_error(exc: Exception, *, max_len: int = 180) -> str:
    text = str(exc).strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def fmt_num(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def csv_to_list(raw: str | None) -> list[str]:
    if raw is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        token = part.strip().upper().replace("$", "")
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out
