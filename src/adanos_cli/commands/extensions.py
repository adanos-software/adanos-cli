"""Completion and plugin helpers."""

from __future__ import annotations

from pathlib import Path

from .. import config as cli_config
from ..utils import CliUsageError


def completion_script(shell: str) -> str:
    command_words = [
        "account",
        "ask",
        "auth",
        "briefing",
        "capabilities",
        "compare",
        "completion",
        "config",
        "consensus",
        "crypto",
        "doctor",
        "endpoint",
        "explain",
        "health",
        "onboard",
        "plugins",
        "scan",
        "search",
        "shell",
        "stats",
        "stock",
        "trending",
        "watchlist",
        "whoami",
    ]
    joined = " ".join(command_words)
    if shell == "bash":
        return (
            "_adanos_completions() {\n"
            "  local current\n"
            "  current=\"${COMP_WORDS[COMP_CWORD]}\"\n"
            f"  COMPREPLY=($(compgen -W '{joined}' -- \"$current\"))\n"
            "}\n"
            "complete -F _adanos_completions adanos\n"
        )
    if shell == "zsh":
        return (
            "#compdef adanos\n"
            "_adanos() {\n"
            f"  local -a commands=({joined})\n"
            "  _describe 'command' commands\n"
            "}\n"
            "compdef _adanos adanos\n"
        )
    if shell == "fish":
        lines = [f"complete -c adanos -f -a '{word}'" for word in command_words]
        return "\n".join(lines) + "\n"
    raise CliUsageError(f"Unsupported shell for completion: {shell}")


def plugins_dir() -> Path:
    return cli_config.CONFIG_DIR / "plugins"


def list_plugin_files() -> list[dict[str, str]]:
    plugin_dir = plugins_dir()
    if not plugin_dir.exists():
        return []
    plugins: list[dict[str, str]] = []
    for path in sorted(plugin_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        plugins.append({"name": path.stem, "path": str(path)})
    return plugins
