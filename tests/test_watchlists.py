"""Watchlist command tests."""

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


def test_watchlist_crud_flow(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)

    assert cli_main.main(["watchlist", "add", "core", "--asset", "stocks", "--symbols", "MSFT", "AAPL", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watchlist_state"
    assert payload["command"] == "watchlist"
    assert payload["subcommand"] == "add"
    assert payload["watchlist"]["stocks"] == ["MSFT", "AAPL"]
    assert payload["core"]["stocks"] == ["MSFT", "AAPL"]

    assert cli_main.main(["watchlist", "add", "core", "--asset", "crypto", "--symbols", "BTC,ETH", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["watchlist"]["crypto"] == ["BTC", "ETH"]
    assert payload["core"]["crypto"] == ["BTC", "ETH"]

    assert cli_main.main(["watchlist", "show", "core", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subcommand"] == "show"
    assert payload["watchlist"]["stocks"] == ["MSFT", "AAPL"]
    assert payload["core"]["stocks"] == ["MSFT", "AAPL"]
    assert payload["core"]["crypto"] == ["BTC", "ETH"]

    assert cli_main.main(["watchlist", "remove", "core", "--asset", "stocks", "--symbols", "AAPL", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subcommand"] == "remove"
    assert payload["core"]["stocks"] == ["MSFT"]

    assert cli_main.main(["watchlist", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watchlist_catalog"
    assert payload["command"] == "watchlist"
    assert payload["subcommand"] == "list"
    assert "watchlists" in payload
    assert "core" in payload

    assert cli_main.main(["watchlist", "delete", "core", "--force", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watchlist_delete_result"
    assert payload["command"] == "watchlist"
    assert payload["subcommand"] == "delete"
    assert payload["deleted"] is True
