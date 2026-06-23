"""CLI endpoint registry coverage tests."""

from __future__ import annotations

from argparse import Namespace

import pytest


from adanos_cli.endpoints import ENDPOINTS, endpoint_paths, invoke_endpoint
from adanos_cli.nlp import parse_ask_intent
from adanos_cli.utils import CliUsageError


NEWS_ENDPOINT_IDS = {
    "news-stocks.trending": {
        "path": "/news/stocks/v1/trending",
        "required": tuple(),
        "optional": ("from", "to", "days", "limit", "offset", "type", "source"),
    },
    "news-stocks.trending.sectors": {
        "path": "/news/stocks/v1/trending/sectors",
        "required": tuple(),
        "optional": ("from", "to", "days", "limit", "offset", "source"),
    },
    "news-stocks.trending.countries": {
        "path": "/news/stocks/v1/trending/countries",
        "required": tuple(),
        "optional": ("from", "to", "days", "limit", "offset", "source"),
    },
    "news-stocks.stock": {
        "path": "/news/stocks/v1/stock/{ticker}",
        "required": ("ticker",),
        "optional": ("from", "to", "days"),
    },
    "news-stocks.stock.mentions": {
        "path": "/news/stocks/v1/stock/{ticker}/mentions",
        "required": ("ticker",),
        "optional": ("from", "to", "days", "limit", "offset"),
    },
    "news-stocks.stock.explain": {
        "path": "/news/stocks/v1/stock/{ticker}/explain",
        "required": ("ticker",),
        "optional": tuple(),
    },
    "news-stocks.search": {
        "path": "/news/stocks/v1/search",
        "required": ("q",),
        "optional": ("limit",),
    },
    "news-stocks.compare": {
        "path": "/news/stocks/v1/compare",
        "required": ("tickers",),
        "optional": ("from", "to", "days"),
    },
    "news-stocks.market-sentiment": {
        "path": "/news/stocks/v1/market-sentiment",
        "required": tuple(),
        "optional": ("from", "to", "days"),
    },
    "news-stocks.stats": {
        "path": "/news/stocks/v1/stats",
        "required": tuple(),
        "optional": tuple(),
    },
    "news-stocks.health": {
        "path": "/news/stocks/v1/health",
        "required": tuple(),
        "optional": tuple(),
    },
}


def test_endpoint_registry_paths_are_unique() -> None:
    assert len(endpoint_paths()) == len(ENDPOINTS)


def test_endpoint_paths_cover_all_supported_platform_families() -> None:
    paths = endpoint_paths()
    assert any(path.startswith("/news/stocks/v1/") for path in paths)
    assert any(path.startswith("/reddit/stocks/v1/") for path in paths)
    assert any(path.startswith("/reddit/crypto/v1/") for path in paths)
    assert any(path.startswith("/x/stocks/v1/") for path in paths)
    assert any(path.startswith("/polymarket/stocks/v1/") for path in paths)


def test_endpoint_count_is_complete() -> None:
    assert len(ENDPOINTS) == 53


def test_root_health_endpoint_spec_is_complete() -> None:
    spec = ENDPOINTS["root.health"]
    assert spec.path == "/health"
    assert spec.required_params == tuple()
    assert spec.optional_params == tuple()


def test_sentiment_analyze_endpoint_spec_is_complete() -> None:
    spec = ENDPOINTS["sentiment.analyze"]
    assert spec.path == "/sentiment/v1/analyze"
    assert spec.required_params == ("text",)
    assert spec.optional_params == tuple()


def test_news_endpoint_specs_are_complete() -> None:
    for endpoint_id, expected in NEWS_ENDPOINT_IDS.items():
        spec = ENDPOINTS[endpoint_id]
        assert spec.path == expected["path"]
        assert spec.required_params == expected["required"]
        assert spec.optional_params == expected["optional"]


def test_x_explain_endpoint_spec_is_complete() -> None:
    spec = ENDPOINTS["x-stocks.stock.explain"]
    assert spec.path == "/x/stocks/v1/stock/{ticker}/explain"
    assert spec.required_params == ("ticker",)
    assert spec.optional_params == tuple()


def test_raw_mention_endpoint_specs_support_offset() -> None:
    expected = {
        "reddit-stocks.stock.mentions": ("from", "to", "days", "limit", "offset", "include_inherited"),
        "news-stocks.stock.mentions": ("from", "to", "days", "limit", "offset"),
        "reddit-crypto.token.mentions": ("from", "to", "days", "limit", "offset", "include_inherited"),
        "x-stocks.stock.mentions": ("from", "to", "days", "limit", "offset"),
        "polymarket-stocks.stock.mentions": ("from", "to", "days", "limit", "offset"),
    }
    for endpoint_id, optional_params in expected.items():
        assert ENDPOINTS[endpoint_id].optional_params == optional_params


def test_invoke_endpoint_rejects_unsupported_source() -> None:
    class DummyNews:
        def search(self, query: str, *, limit: int = 20) -> dict[str, str | int]:
            return {"query": query}

    class DummyClient:
        news = DummyNews()

    with pytest.raises(CliUsageError, match="does not support --source"):
        invoke_endpoint(DummyClient(), "news-stocks.search", Namespace(q="Tesla", source="wsj"))


def test_invoke_endpoint_search_passes_limit_only() -> None:
    class DummyNews:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, *, limit: int = 20) -> dict[str, int | str]:
            self.calls.append((query, limit))
            return {"query": query, "count": 1}

    class DummyClient:
        def __init__(self) -> None:
            self.news = DummyNews()

    client = DummyClient()
    invoke_endpoint(client, "news-stocks.search", Namespace(q="Tesla", days=14, from_="2026-05-01", to="2026-05-07", limit=5, source=None))
    assert client.news.calls == [("Tesla", 5)]


def test_search_endpoint_specs_accept_limit_only() -> None:
    for endpoint_id in (
        "news-stocks.search",
        "reddit-stocks.search",
        "reddit-crypto.search",
        "x-stocks.search",
        "polymarket-stocks.search",
    ):
        assert ENDPOINTS[endpoint_id].optional_params == ("limit",)


def test_invoke_endpoint_rejects_days_with_full_date_window() -> None:
    class DummyNews:
        def trending(self, **kwargs):
            return kwargs

    class DummyClient:
        news = DummyNews()

    with pytest.raises(CliUsageError, match="do not combine --days"):
        invoke_endpoint(
            DummyClient(),
            "news-stocks.trending",
            Namespace(days=7, from_="2026-05-01", to="2026-05-07", limit=5, offset=0, type=None, source=None),
        )


def test_invoke_endpoint_market_sentiment_passes_days() -> None:
    class DummyNews:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def market_sentiment(self, *, days: int = 1) -> dict[str, int]:
            self.calls.append(days)
            return {"days": days}

    class DummyClient:
        def __init__(self) -> None:
            self.news = DummyNews()

    client = DummyClient()
    invoke_endpoint(client, "news-stocks.market-sentiment", Namespace(days=9, source=None))
    assert client.news.calls == [9]


def test_invoke_endpoint_x_explain_passes_ticker() -> None:
    class DummyX:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def explain(self, ticker: str) -> dict[str, str]:
            self.calls.append(ticker)
            return {"ticker": ticker, "explanation": "X context"}

    class DummyClient:
        def __init__(self) -> None:
            self.x = DummyX()

    client = DummyClient()
    result = invoke_endpoint(client, "x-stocks.stock.explain", Namespace(ticker="NVDA", source=None))
    assert result == {"ticker": "NVDA", "explanation": "X context"}
    assert client.x.calls == ["NVDA"]


def test_invoke_endpoint_sentiment_analyze_passes_text() -> None:
    class DummySentiment:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def analyze(self, text: str) -> dict[str, str]:
            self.calls.append(text)
            return {"sentiment_label": "positive"}

    class DummyClient:
        def __init__(self) -> None:
            self.sentiment = DummySentiment()

    client = DummyClient()
    result = invoke_endpoint(client, "sentiment.analyze", Namespace(text="TSLA squeeze setup", source=None))
    assert result == {"sentiment_label": "positive"}
    assert client.sentiment.calls == ["TSLA squeeze setup"]


def test_invoke_endpoint_raw_mentions_passes_params() -> None:
    class DummyReddit:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int, int, int, bool]] = []

        def mentions(
            self,
            ticker: str,
            *,
            days: int = 7,
            limit: int = 100,
            offset: int = 0,
            include_inherited: bool = False,
        ) -> dict[str, str]:
            self.calls.append((ticker, days, limit, offset, include_inherited))
            return {"ticker": ticker}

    class DummyClient:
        def __init__(self) -> None:
            self.reddit = DummyReddit()

    client = DummyClient()
    result = invoke_endpoint(
        client,
        "reddit-stocks.stock.mentions",
        Namespace(ticker="TSLA", days=14, limit=25, offset=50, include_inherited=True, source=None),
    )
    assert result == {"ticker": "TSLA"}
    assert client.reddit.calls == [("TSLA", 14, 25, 50, True)]


def test_invoke_endpoint_root_health_uses_raw_sdk_http() -> None:
    class DummyResponse:
        content = b'{"status":"ok"}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"status": "ok"}

    class DummyHttp:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def request(self, method: str, path: str) -> DummyResponse:
            self.calls.append((method, path))
            return DummyResponse()

    class DummySdkClient:
        def __init__(self) -> None:
            self.http = DummyHttp()

        def get_httpx_client(self) -> DummyHttp:
            return self.http

    class DummyClient:
        def __init__(self) -> None:
            self._client = DummySdkClient()

    client = DummyClient()
    result = invoke_endpoint(client, "root.health", Namespace(source=None))
    assert result == {"status": "ok"}
    assert client._client.http.calls == [("get", "/health")]


def test_nlp_detects_stock_intent() -> None:
    intent = parse_ask_intent("how does stock TSLA look")
    assert intent.kind == "stock_report"
    assert intent.primary == "TSLA"


def test_nlp_detects_crypto_pair_intent() -> None:
    intent = parse_ask_intent("crypto btc/eth")
    assert intent.kind == "crypto_compare"
    assert intent.primary == "BTC"
    assert intent.secondary == "ETH"


def test_nlp_ignores_label_tokens_in_english_prompt() -> None:
    intent = parse_ask_intent("stock TSLA")
    assert intent.kind == "stock_report"
    assert intent.primary == "TSLA"


def test_nlp_ignores_filler_words_for_company_prompt() -> None:
    intent = parse_ask_intent("how many users talk about Microsoft?")
    assert intent.kind == "stock_report"
    assert intent.primary == "MICROSOFT"


def test_nlp_detects_stock_compare_prompt() -> None:
    intent = parse_ask_intent("TSLA vs NVDA")
    assert intent.kind == "stock_compare"
    assert intent.primary == "TSLA"
    assert intent.secondary == "NVDA"


def test_nlp_detects_trending_stocks_prompt() -> None:
    intent = parse_ask_intent("top trending stocks today")
    assert intent.kind == "trending_report"
    assert intent.primary == "stocks"


def test_nlp_detects_trending_crypto_prompt() -> None:
    intent = parse_ask_intent("top trending crypto today")
    assert intent.kind == "trending_report"
    assert intent.primary == "crypto"


def test_nlp_detects_crypto_compare_without_keyword_when_symbols_are_common() -> None:
    intent = parse_ask_intent("BTC vs ETH")
    assert intent.kind == "crypto_compare"
    assert intent.primary == "BTC"
    assert intent.secondary == "ETH"


def test_nlp_detects_scan_intent() -> None:
    intent = parse_ask_intent("scan crypto for setups")
    assert intent.kind == "scan_report"
    assert intent.primary == "crypto"


def test_nlp_detects_briefing_intent_with_profile() -> None:
    intent = parse_ask_intent("please create a daytrader briefing")
    assert intent.kind == "briefing_report"
    assert intent.primary == "daytrader"


def test_nlp_detects_watchlist_intent() -> None:
    intent = parse_ask_intent("watchlist core report crypto")
    assert intent.kind == "watchlist_report"
    assert intent.primary == "core"
    assert intent.secondary == "crypto"


def test_nlp_maps_crypto_name_to_symbol() -> None:
    intent = parse_ask_intent("crypto bitcoin")
    assert intent.kind == "crypto_report"
    assert intent.primary == "BTC"


def test_nlp_ignores_english_mention_verb_for_company_prompt() -> None:
    intent = parse_ask_intent("How many users mention Microsoft?")
    assert intent.kind == "stock_report"
    assert intent.primary == "MICROSOFT"
