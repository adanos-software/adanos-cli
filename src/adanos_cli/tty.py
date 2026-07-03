"""TTY and output-mode helpers."""

from __future__ import annotations

import os
import sys
from argparse import Namespace


def stdin_is_tty() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def stdout_is_tty() -> bool:
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def is_interactive() -> bool:
    if not stdin_is_tty() or not stdout_is_tty():
        return False
    if str(os.getenv("CI") or "").strip().lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("GITHUB_ACTIONS"):
        return False
    if str(os.getenv("TERM") or "").strip().lower() == "dumb":
        return False
    return True


def supports_color() -> bool:
    if not stdout_is_tty():
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    term = str(os.getenv("TERM") or "").strip().lower()
    if not term or term == "dumb":
        return False
    return True


def should_output_json(args: Namespace, *, argv_supplied: bool) -> bool:
    output_mode = getattr(args, "output", None)
    if output_mode == "json":
        return True
    if bool(getattr(args, "json", False)):
        return True
    if bool(getattr(args, "quiet", False)):
        return True
    if bool(getattr(args, "plain", False)):
        return False
    if output_mode == "text":
        return False
    if argv_supplied:
        return False
    return not stdout_is_tty()
