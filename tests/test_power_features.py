"""Power user workflow tests (scan, briefing, watchlist report)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

import adanos_cli.config as cli_config
import adanos_cli.main as cli_main
from adanos_cli.summaries import build_crypto_report, build_stock_report


def _isolate_config(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".config" / "adanos-cli"
    cfg_path = cfg_dir / "config.json"
    credentials_path = cfg_dir / "credentials.json"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", credentials_path)


class _RedditNS:
    def trending(self, *, days: int = 1, limit: int = 20, offset: int = 0, type=None):
        return [
            {"ticker": "MSFT", "buzz_score": 80.0, "mentions": 120, "sentiment_score": 0.11},
            {"ticker": "AAPL", "buzz_score": 76.0, "mentions": 90, "sentiment_score": 0.08},
        ][:limit]

    def compare(self, tickers, *, days: int = 7):
        rows = []
        for ticker in tickers:
            rows.append({"ticker": ticker, "buzz_score": 70.0, "mentions": 100, "sentiment_score": 0.1})
        return {"period_days": days, "stocks": rows}

    def stock(self, ticker: str, *, days: int = 7):
        return {"ticker": ticker, "found": True, "buzz_score": 70.0, "trend": "rising", "mentions": 100, "sentiment_score": 0.1}

    def explain(self, ticker: str):
        return {"ticker": ticker, "explanation": f"{ticker} explanation"}

    def search(self, query: str, *, limit: int = 20):
        return {
            "query": query,
            "count": 1,
            "period_days": 7,
            "results": [{"ticker": "MSFT", "name": "Microsoft Corporation"}][:limit],
        }

    def trending_sectors(self, *, days: int = 1, limit: int = 20, offset: int = 0):
        return [{"sector": "Technology", "buzz_score": 82.0}]

    def trending_countries(self, *, days: int = 1, limit: int = 20, offset: int = 0):
        return [{"country": "United States", "buzz_score": 80.0}]


class _NewsNS:
    def trending(self, *, days: int = 1, limit: int = 20, offset: int = 0, type=None, source=None):
        return [
            {"ticker": "MSFT", "buzz_score": 74.0, "mentions": 80, "sentiment_score": 0.09},
            {"ticker": "AAPL", "buzz_score": 70.0, "mentions": 60, "sentiment_score": 0.05},
        ][:limit]

    def compare(self, tickers, *, days: int = 7):
        return {"period_days": days, "stocks": [{"ticker": t, "buzz_score": 72.0, "mentions": 85, "sentiment_score": 0.08} for t in tickers]}

    def stock(self, ticker: str, *, days: int = 7):
        return {"ticker": ticker, "found": True, "buzz_score": 72.0, "trend": "stable", "mentions": 85, "sentiment_score": 0.08}

    def explain(self, ticker: str):
        return {"ticker": ticker, "explanation": f"{ticker} news backdrop"}

    def search(self, query: str, *, limit: int = 20):
        return {
            "query": query,
            "count": 1,
            "period_days": 7,
            "results": [{"ticker": "MSFT", "name": "Microsoft Corporation"}][:limit],
        }

    def trending_sectors(self, *, days: int = 1, limit: int = 20, offset: int = 0, source=None):
        return [{"sector": "Technology", "buzz_score": 75.0}]

    def trending_countries(self, *, days: int = 1, limit: int = 20, offset: int = 0, source=None):
        return [{"country": "United States", "buzz_score": 74.0}]


class _XNS:
    def trending(self, *, days: int = 1, limit: int = 20, offset: int = 0, type=None):
        return [{"ticker": "MSFT", "buzz_score": 84.0, "mentions": 300, "sentiment_score": 0.15}][:limit]

    def compare(self, tickers, *, days: int = 7):
        return {"period_days": days, "stocks": [{"ticker": t, "buzz_score": 82.0, "mentions": 200, "sentiment_score": 0.12} for t in tickers]}

    def stock(self, ticker: str, *, days: int = 7):
        return {"ticker": ticker, "buzz_score": 82.0, "trend": "stable", "mentions": 200, "sentiment_score": 0.12}

    def explain(self, ticker: str):
        return {"ticker": ticker, "explanation": f"{ticker} X discussion"}

    def search(self, query: str, *, limit: int = 20):
        return {
            "query": query,
            "count": 1,
            "period_days": 7,
            "results": [{"ticker": "MSFT", "name": "Microsoft Corporation"}][:limit],
        }


class _PolymarketNS:
    def trending(self, *, days: int = 1, limit: int = 20, offset: int = 0, type=None):
        return [{"ticker": "MSFT", "buzz_score": 79.0, "trade_count": 500, "sentiment_score": 0.2}][:limit]

    def compare(self, tickers, *, days: int = 7):
        return {"period_days": days, "stocks": [{"ticker": t, "buzz_score": 79.0, "trade_count": 500, "sentiment_score": 0.2} for t in tickers]}

    def stock(self, ticker: str, *, days: int = 7):
        return {
            "ticker": ticker,
            "found": True,
            "buzz_score": 79.0,
            "trend": "rising",
            "trade_count": 500,
            "sentiment_score": 0.2,
            "market_count": 8,
            "current_market_count": 3,
            "pulse": {
                "mood": "bullish",
                "confidence": 0.72,
                "thin_data": False,
                "why": "Market evidence leans positive.",
                "warnings": ["small sample"],
                "evidence": [{"condition_id": "abc"}],
            },
            "daily_trend": [{"date": "2026-06-28", "bullish_pct": 66.7, "bearish_pct": 33.3}],
            "top_mentions": [
                {
                    "condition_id": "abc",
                    "question": "Will MSFT close higher?",
                    "market_status": "active",
                    "sentiment_score": 0.4,
                }
            ],
        }

    def search(self, query: str, *, limit: int = 20):
        return {
            "query": query,
            "count": 1,
            "period_days": 7,
            "results": [{"ticker": "MSFT", "name": "Microsoft Corporation"}][:limit],
        }


class _CryptoNS:
    def trending(self, *, days: int = 1, limit: int = 20, offset: int = 0):
        return [{"symbol": "BTC", "buzz_score": 78.0, "mentions": 1000, "sentiment_score": 0.05, "total_upvotes": 5000}][:limit]

    def compare(self, symbols, *, days: int = 7):
        return {"period_days": days, "tokens": [{"symbol": s, "buzz_score": 78.0, "mentions": 1000, "sentiment_score": 0.05, "total_upvotes": 5000} for s in symbols]}

    def token(self, symbol: str, *, days: int = 7):
        return {"symbol": symbol, "found": True, "buzz_score": 78.0, "mentions": 1000, "sentiment_score": 0.05}

    def search(self, query: str, *, limit: int = 20):
        return {
            "query": query,
            "count": 1,
            "period_days": 7,
            "results": [{"symbol": "BTC", "name": "Bitcoin"}][:limit],
        }

    def stats(self):
        return {"unique_tokens": 100, "supported_tokens": 1000}


class _FakeClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.news = _NewsNS()
        self.reddit = _RedditNS()
        self.x = _XNS()
        self.polymarket = _PolymarketNS()
        self.crypto = _CryptoNS()

    def close(self):
        return None


class _UnauthorizedReddit:
    def trending(self, *, days: int = 1, limit: int = 20, offset: int = 0, type=None):
        request = httpx.Request("GET", "https://api.adanos.org/reddit/stocks/v1/trending")
        response = httpx.Response(401, json={"detail": "Invalid API key"}, request=request)
        raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)


class _UnauthorizedClient(_FakeClient):
    def __init__(self, api_key: str, base_url: str):
        super().__init__(api_key, base_url)
        self.reddit = _UnauthorizedReddit()


class _BrokenNS:
    def stock(self, ticker: str, *, days: int = 7):
        raise ConnectionRefusedError("[Errno 61] Connection refused")

    def explain(self, ticker: str):
        raise ConnectionRefusedError("[Errno 61] Connection refused")


class _BrokenClient:
    news = _BrokenNS()
    reddit = _BrokenNS()
    x = _BrokenNS()
    polymarket = _BrokenNS()


def test_scan_briefing_and_watchlist_report(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    rc = cli_main.main(
        ["--api-key", "adanos_key_test", "scan", "--asset", "stocks", "--style", "daytrader", "--top", "1", "--json"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "stock_scan"
    assert payload["top"] == 1
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["ticker"] == "MSFT"
    assert payload["rows"][0]["signal"] in {"bullish", "neutral", "hot"}
    assert payload["style"] == "daytrader"
    assert payload["applied_filters"]["min_platforms"] == 2

    rc = cli_main.main(["--api-key", "adanos_key_test", "briefing", "--profile", "investor", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "briefing"
    assert payload["profile"] == "investor"
    assert "stocks_scan" in payload
    assert "reddit_sectors" in payload
    assert "playbook" in payload

    assert cli_main.main(["watchlist", "add", "core", "--asset", "stocks", "--symbols", "MSFT,AAPL"]) == 0
    assert cli_main.main(["watchlist", "add", "core", "--asset", "crypto", "--symbols", "BTC,ETH"]) == 0
    capsys.readouterr()

    rc = cli_main.main(["--api-key", "adanos_key_test", "watchlist", "report", "core", "--asset", "stocks", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watchlist_report"
    assert payload["asset"] == "stocks"
    assert payload["symbols"] == ["MSFT", "AAPL"]
    assert payload["report"]["kind"] == "stock_compare"
    assert payload["report"]["tickers"] == ["MSFT", "AAPL"]

    rc = cli_main.main(["--api-key", "adanos_key_test", "watchlist", "report", "core", "--asset", "all", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watchlist_report"
    assert payload["asset"] == "all"
    assert "stocks" in payload
    assert "crypto" in payload

    rc = cli_main.main(
        [
            "--api-key",
            "adanos_key_test",
            "briefing",
            "--profile",
            "portfolio",
            "--from-watchlist",
            "core",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "portfolio"
    assert payload["stock_focus"]["tickers"] == ["MSFT", "AAPL"]
    assert payload["crypto_focus"]["symbols"] == ["BTC", "ETH"]


def test_stock_report_network_errors_are_friendly() -> None:
    report = build_stock_report(_BrokenClient(), "TSLA", days=7)

    assert report["news"]["ok"] is False
    assert report["news"]["error"].startswith("Cannot reach API base URL.")
    assert "[Errno 61]" not in report["news"]["error"]


def test_search_command_accepts_limit(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    rc = cli_main.main(
        [
            "--api-key",
            "adanos_key_test",
            "search",
            "--platform",
            "news-stocks",
            "Tesla",
            "--limit",
            "1",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "endpoint_result"
    assert payload["endpoint"] == "news-stocks.search"
    assert payload["data"]["query"] == "Tesla"
    assert payload["result_count"] == 1


def test_data_command_401_exits_as_auth_error(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _UnauthorizedClient)

    rc = cli_main.main(["--api-key", "adanos_key_test", "trending", "--platform", "reddit-stocks", "--json"])
    payload = json.loads(capsys.readouterr().err)

    assert rc == 2
    assert payload["error"]["code"] == "auth_failed"
    assert payload["error"]["status_code"] == 401


def test_crypto_report_search_uses_api_managed_window() -> None:
    report = build_crypto_report(_FakeClient("adanos_key_test", "https://api.adanos.org"), "BTC", days=7)

    assert report["reddit_crypto"]["ok"] is True
    assert report["search"]["ok"] is True
    assert report["search"]["data"]["query"] == "BTC"


def test_ask_routes_scan_briefing_and_watchlist(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    assert cli_main.main(["watchlist", "add", "core", "--asset", "stocks", "--symbols", "MSFT,AAPL"]) == 0
    assert cli_main.main(["watchlist", "add", "core", "--asset", "crypto", "--symbols", "BTC,ETH"]) == 0
    capsys.readouterr()

    rc = cli_main.main(["--api-key", "adanos_key_test", "--output", "json", "ask", "scan", "crypto"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "crypto_scan"

    rc = cli_main.main(["--api-key", "adanos_key_test", "--output", "json", "ask", "briefing", "for", "daytrader"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "briefing"
    assert payload["profile"] == "daytrader"

    rc = cli_main.main(["--api-key", "adanos_key_test", "--output", "json", "ask", "watchlist", "core", "report"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watchlist_report"
    assert payload["name"] == "core"


def test_ask_routes_common_crypto_symbols_to_crypto_reports(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    for prompt, expected_kind in (
        ("How does BTC look?", "crypto_report"),
        ("How does ETH look?", "crypto_report"),
        ("How does SOL look?", "crypto_report"),
        ("compare BTC and ETH", "crypto_compare"),
    ):
        rc = cli_main.main(["--api-key", "adanos_key_test", "ask", prompt, "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["kind"] == expected_kind
        assert payload["command"] == "ask"

    rc = cli_main.main(["--api-key", "adanos_key_test", "ask", "How does TSLA look?", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["kind"] == "stock_report"
    assert payload["command"] == "ask"


def test_ask_routes_unseparated_stock_list_to_multi_stock_compare(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)
    monkeypatch.setattr(
        cli_main,
        "_resolve_stock_ticker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("explicit tickers must not trigger search")),
    )

    rc = cli_main.main(
        [
            "--api-key",
            "adanos_key_test",
            "ask",
            "compare",
            "NVDA",
            "TSLA",
            "AAPL",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["kind"] == "stock_compare"
    assert payload["command"] == "ask"
    assert payload["tickers"] == ["NVDA", "TSLA", "AAPL"]


def test_ask_compare_canonicalizes_dollar_prefixed_tickers(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)
    monkeypatch.setattr(
        cli_main,
        "_resolve_stock_ticker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("explicit tickers must not trigger search")),
    )

    rc = cli_main.main(["--api-key", "adanos_key_test", "ask", "compare", "$NVDA", "$TSLA", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["tickers"] == ["NVDA", "TSLA"]


def test_ask_positional_json_after_terminator_stays_text(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    rc = cli_main.main(["--api-key", "adanos_key_test", "ask", "--", "--json"])
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out
    assert not captured.out.lstrip().startswith("{")


def test_ask_compare_preserves_vs_ticker() -> None:
    intent = cli_main.parse_ask_intent("compare NVDA AAPL VS")

    assert intent.kind == "stock_compare"
    assert intent.assets == ("NVDA", "AAPL", "VS")


def test_consensus_and_explain_reports(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    rc = cli_main.main(["--api-key", "adanos_key_test", "consensus", "MSFT", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "consensus_report"
    assert payload["command"] == "consensus"
    assert payload["ticker"] == "MSFT"
    assert payload["sources_covered"] == 4
    assert payload["signal"] in {"bullish", "neutral", "hot"}

    rc = cli_main.main(["--api-key", "adanos_key_test", "consensus", "MSFT"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "data_confidence=" in out
    assert "tracked_activity=" in out
    assert "Polymarket" in out and "trades=" in out

    rc = cli_main.main(["--api-key", "adanos_key_test", "explain", "MSFT", "--profile", "daytrader", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "explain_report"
    assert payload["command"] == "explain"
    assert payload["profile"] == "daytrader"
    assert "MSFT" in payload["headline"]
    assert payload["x_context"] == "MSFT X discussion"
    assert payload["consensus"]["kind"] == "consensus_report"

    rc = cli_main.main(["--api-key", "adanos_key_test", "stock", "MSFT"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "X/Twitter Explain: MSFT X discussion" in out
    assert "pulse: mood=bullish" in out
    assert "market breadth: period=8, current_active=3" in out
    assert "bullish_pct=66.70" in out
    assert "representative market evidence" in out


def test_watch_and_export_workflows(tmp_path, monkeypatch, capsys) -> None:
    _isolate_config(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "_load_sdk_client_class", lambda: _FakeClient)

    assert cli_main.main(["watchlist", "add", "core", "--asset", "stocks", "--symbols", "MSFT,AAPL"]) == 0
    assert cli_main.main(["watchlist", "add", "core", "--asset", "crypto", "--symbols", "BTC,ETH"]) == 0
    capsys.readouterr()

    rc = cli_main.main(
        [
            "--api-key",
            "adanos_key_test",
            "watch",
            "core",
            "--kind",
            "watchlist",
            "--asset",
            "all",
            "--iterations",
            "1",
            "--refresh",
            "1",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "watch"
    assert payload["command"] == "watch"
    assert payload["report_kind"] == "watchlist"
    assert payload["iterations"] == 1
    assert payload["snapshots"][0]["report"]["kind"] == "watchlist_report"

    rc = cli_main.main(
        [
            "--api-key",
            "adanos_key_test",
            "export",
            "MSFT",
            "--kind",
            "consensus",
            "--format",
            "csv",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("source,label,ok,found,buzz_score,sentiment,volume,trend")

    rc = cli_main.main(
        [
            "--api-key",
            "adanos_key_test",
            "export",
            "MSFT",
            "--kind",
            "stock",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "stock_report"
    assert payload["command"] == "export"
    assert payload["subcommand"] == "stock"
