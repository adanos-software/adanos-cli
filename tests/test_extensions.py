"""Completion and plugin discovery tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


import adanos_cli.config as cli_config
import adanos_cli.main as cli_main


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)


def test_completion_bash(capsys) -> None:
    rc = cli_main.main(["completion", "bash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "_adanos_completions()" in out
    assert "complete -F _adanos_completions adanos" in out


def test_plugins_list_json(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    plugin_dir = cli_config.CONFIG_DIR / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "watchdog.py").write_text("PLUGIN = True\n", encoding="utf-8")

    rc = cli_main.main(["--output", "json", "plugins", "list"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "plugins_list"
    assert payload["plugins"] == [
        {
            "name": "watchdog",
            "path": str(plugin_dir / "watchdog.py"),
        }
    ]
