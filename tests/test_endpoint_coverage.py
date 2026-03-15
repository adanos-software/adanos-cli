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
        "optional": ("days", "limit", "offset", "type", "source"),
    },
    "news-stocks.trending.sectors": {
        "path": "/news/stocks/v1/trending/sectors",
        "required": tuple(),
        "optional": ("days", "limit", "offset", "source"),
    },
    "news-stocks.trending.countries": {
        "path": "/news/stocks/v1/trending/countries",
        "required": tuple(),
        "optional": ("days", "limit", "offset", "source"),
    },
    "news-stocks.stock": {
        "path": "/news/stocks/v1/stock/{ticker}",
        "required": ("ticker",),
        "optional": ("days",),
    },
    "news-stocks.stock.explain": {
        "path": "/news/stocks/v1/stock/{ticker}/explain",
        "required": ("ticker",),
        "optional": tuple(),
    },
    "news-stocks.search": {
        "path": "/news/stocks/v1/search",
        "required": ("q",),
        "optional": tuple(),
    },
    "news-stocks.compare": {
        "path": "/news/stocks/v1/compare",
        "required": ("tickers",),
        "optional": ("days",),
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
    assert len(ENDPOINTS) == 40


def test_news_endpoint_specs_are_complete() -> None:
    for endpoint_id, expected in NEWS_ENDPOINT_IDS.items():
        spec = ENDPOINTS[endpoint_id]
        assert spec.path == expected["path"]
        assert spec.required_params == expected["required"]
        assert spec.optional_params == expected["optional"]


def test_invoke_endpoint_rejects_unsupported_source() -> None:
    class DummyNews:
        def search(self, query: str) -> dict[str, str]:
            return {"query": query}

    class DummyClient:
        news = DummyNews()

    with pytest.raises(CliUsageError, match="does not support --source"):
        invoke_endpoint(DummyClient(), "news-stocks.search", Namespace(q="Tesla", source="wsj"))


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
