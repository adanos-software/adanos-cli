"""Persistent shell history helpers."""

from __future__ import annotations

from pathlib import Path

from . import config as cli_config

SHELL_HISTORY_LIMIT = 200


def history_path() -> Path:
    return cli_config.CONFIG_DIR / "shell_history"


def load_history(*, limit: int | None = None) -> list[str]:
    path = history_path()
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit is None or limit >= len(lines):
        return lines
    return lines[-limit:]


def append_history(command: str) -> None:
    normalized = command.strip()
    if not normalized:
        return
    lines = load_history()
    lines.append(normalized)
    trimmed = lines[-SHELL_HISTORY_LIMIT:]
    cli_config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    history_path().write_text("\n".join(trimmed) + "\n", encoding="utf-8")


def most_recent_command() -> str | None:
    history = load_history(limit=1)
    return history[-1] if history else None
