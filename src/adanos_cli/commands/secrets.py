"""Secret input helpers for command handlers."""

from __future__ import annotations

import sys
from argparse import Namespace
from getpass import getpass
from pathlib import Path

from ..tty import is_interactive
from ..utils import CliUsageError


def read_api_key_arg(args: Namespace) -> str:
    sources = [
        name
        for name in ("api_key", "api_key_file", "api_key_stdin")
        if bool(getattr(args, name, None))
    ]
    if len(sources) > 1:
        raise CliUsageError("Use only one API key input source: --api-key, --api-key-file, or --api-key-stdin.")

    api_key = str(getattr(args, "api_key", "") or "").strip()
    if api_key:
        return api_key

    api_key_file = str(getattr(args, "api_key_file", "") or "").strip()
    if api_key_file:
        try:
            value = Path(api_key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CliUsageError(f"Could not read API key file: {exc}") from exc
        if not value:
            raise CliUsageError("API key file is empty.")
        return value

    if bool(getattr(args, "api_key_stdin", False)):
        value = sys.stdin.readline().strip()
        if not value:
            raise CliUsageError("No API key received on stdin.")
        return value

    if bool(getattr(args, "no_input", False)):
        raise CliUsageError("API key required with --no-input. Use --api-key-stdin or --api-key-file.")

    if not is_interactive():
        raise CliUsageError("Non-interactive usage requires --api-key, --api-key-file, or --api-key-stdin.")

    value = getpass("API key: ").strip()
    if not value:
        raise CliUsageError("API key must not be empty.")
    return value
