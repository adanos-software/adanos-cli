"""Agent-friendly CLI contract tests."""

from __future__ import annotations

from argparse import Namespace
import json
import sys
from pathlib import Path

import pytest

import adanos_cli.config as cli_config  # noqa: E402
import adanos_cli.main as cli_main  # noqa: E402
from adanos_cli import __version__  # noqa: E402
from adanos_cli.endpoints import ENDPOINTS  # noqa: E402
from adanos_cli.utils import CliUsageError  # noqa: E402


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)


def test_version_json(capsys) -> None:
    rc = cli_main.main(["--output", "json", "--version"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["kind"] == "version"
    assert payload["command"] == "version"
    assert payload["name"] == "adanos-cli"
    assert payload["version"] == __version__


def test_capabilities_json(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    rc = cli_main.main(["--output", "json", "capabilities"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["kind"] == "capabilities"
    assert payload["command"] == "capabilities"
    assert payload["name"] == "adanos-cli"
    assert payload["endpoint_count"] == len(ENDPOINTS)
    assert payload["error_channel"] == "stderr"
    assert payload["output_modes"] == ["text", "json"]
    assert "shell" in payload["commands"]


def test_missing_api_key_emits_json_error_on_stderr(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)
    rc = cli_main.main(["--output", "json", "ask", "stock", "TSLA"])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "api_key_missing"


def test_global_output_json_applies_to_endpoint_list(capsys) -> None:
    rc = cli_main.main(["--output", "json", "endpoint", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert payload[0]["kind"] == "endpoint_spec"
    assert payload[0]["command"] == "endpoint"
    assert payload[0]["subcommand"] == "list"
    assert any(row["id"] == "reddit-stocks.trending" for row in payload)


def test_global_output_json_after_subcommand_is_accepted(capsys) -> None:
    rc = cli_main.main(["capabilities", "--output", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["name"] == "adanos-cli"


def test_endpoint_list_output_json_after_subcommand_is_accepted(capsys) -> None:
    rc = cli_main.main(["endpoint", "list", "--output", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, list)
    assert any(row["id"] == "reddit-stocks.trending" for row in payload)


def test_endpoint_result_wrapper_includes_stable_metadata(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "invoke_endpoint",
        lambda client, endpoint_id, args: [{"ticker": "MSFT"}, {"ticker": "AAPL"}],
    )

    cli_main._call_and_emit_endpoint(
        object(),
        "news-stocks.trending",
        Namespace(days=1, limit=2),
        json_mode=True,
        command="trending",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "endpoint_result"
    assert payload["command"] == "trending"
    assert payload["platform"] == "news-stocks"
    assert payload["route"] == "trending"
    assert payload["endpoint"] == "news-stocks.trending"
    assert payload["result_count"] == 2
    assert len(payload["data"]) == 2


def test_trending_stocks_dimension_alias_routes_to_main_endpoint(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "_call_and_emit_endpoint",
        lambda client, endpoint_id, args, **kwargs: print(json.dumps({"endpoint": endpoint_id, "dimension": args.dimension})),
    )

    cli_main._run_trending(
        object(),
        Namespace(platform="reddit-stocks", dimension="stocks", days=1, limit=2, offset=0, type=None, source=None, json=True),
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"endpoint": "reddit-stocks.trending", "dimension": "stocks"}


def test_health_all_json_includes_stable_metadata(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_main, "invoke_endpoint", lambda client, endpoint_id, args: {"ok": True, "endpoint": endpoint_id})

    cli_main._run_health(object(), Namespace(platform="all", json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "multi_platform_health"
    assert payload["command"] == "health"
    assert payload["platform"] == "all"
    assert "checks" in payload
    assert "root.health" in payload["checks"]
    assert "news-stocks.health" in payload["checks"]
    assert "news-stocks.health" in payload


def test_health_root_routes_to_root_endpoint(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "_call_and_emit_endpoint",
        lambda client, endpoint_id, args, **kwargs: print(json.dumps({"endpoint": endpoint_id})),
    )

    cli_main._run_health(object(), Namespace(platform="root", json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"endpoint": "root.health"}


class _SearchNamespace:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def search(self, query: str, *, days: int = 7, limit: int = 20):
        query_upper = query.upper()
        matched = []
        for row in self._rows:
            name = str(row.get("name") or "").upper()
            aliases = [str(alias).upper() for alias in row.get("aliases", [])]
            ticker = str(row.get("ticker") or "").upper()
            if query_upper in name or query_upper in ticker or any(query_upper in alias for alias in aliases):
                matched.append(row)
        return {"query": query, "count": len(matched), "period_days": days, "results": matched[:limit]}


class _AliasClient:
    def __init__(self):
        rows = [{"ticker": "MSFT", "name": "Microsoft Corporation"}]
        self.reddit = _SearchNamespace(rows)
        self.x = _SearchNamespace(rows)
        self.polymarket = _SearchNamespace(rows)


def test_alias_resolution_resolves_company_name_to_ticker() -> None:
    client = _AliasClient()
    ticker, query, source = cli_main._resolve_stock_ticker(
        client,
        "how many users talk about Microsoft?",
        "MICROSOFT",
    )
    assert ticker == "MSFT"
    assert query == "MICROSOFT"
    assert source in {"reddit", "x", "polymarket"}


def test_missing_python_sdk_dependency_emits_clear_usage_error(monkeypatch) -> None:
    original_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "adanos":
            raise ImportError("No module named 'adanos'")
        if name == "stocksentiment":
            raise ImportError("No module named 'stocksentiment'")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "adanos", raising=False)
    monkeypatch.delitem(sys.modules, "stocksentiment", raising=False)
    monkeypatch.setattr("builtins.__import__", _fake_import)

    with pytest.raises(CliUsageError, match="Python SDK dependency missing"):
        cli_main._load_sdk_client_class()
