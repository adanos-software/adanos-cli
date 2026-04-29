"""Endpoint registry and invocation for the Adanos CLI.

This module intentionally mirrors the API OpenAPI paths 1:1.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from typing import Any, Callable

from .utils import CliUsageError, csv_to_list


@dataclass(frozen=True)
class EndpointSpec:
    endpoint_id: str
    path: str
    description: str
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    invoke: Callable[[Any, Namespace], Any]


def _with_default(value: Any, default: Any) -> Any:
    return default if value is None else value


def _require_str(args: Namespace, *names: str) -> str:
    for name in names:
        value = getattr(args, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    joined = ", ".join(names)
    raise CliUsageError(f"Required parameter missing: {joined}")


def _require_tickers(args: Namespace) -> list[str]:
    values = csv_to_list(getattr(args, "tickers", None) or getattr(args, "assets", None))
    if not values:
        raise CliUsageError("Required parameter missing: tickers (comma-separated)")
    return values


def _require_symbols(args: Namespace) -> list[str]:
    values = csv_to_list(getattr(args, "symbols", None) or getattr(args, "assets", None))
    if not values:
        raise CliUsageError("Required parameter missing: symbols (comma-separated)")
    return values


# --- Reddit Stocks ---

def _reddit_stocks_trending(client: Any, args: Namespace) -> Any:
    return client.reddit.trending(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
        type=args.type,
    )


def _reddit_stocks_trending_sectors(client: Any, args: Namespace) -> Any:
    return client.reddit.trending_sectors(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _reddit_stocks_trending_countries(client: Any, args: Namespace) -> Any:
    return client.reddit.trending_countries(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _reddit_stocks_stock(client: Any, args: Namespace) -> Any:
    return client.reddit.stock(_require_str(args, "ticker"), days=_with_default(args.days, 7))


def _reddit_stocks_mentions(client: Any, args: Namespace) -> Any:
    return client.reddit.mentions(
        _require_str(args, "ticker"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 100),
        include_inherited=bool(getattr(args, "include_inherited", False)),
    )


def _reddit_stocks_explain(client: Any, args: Namespace) -> Any:
    return client.reddit.explain(_require_str(args, "ticker"))


def _reddit_stocks_search(client: Any, args: Namespace) -> Any:
    return client.reddit.search(
        _require_str(args, "q", "query"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 20),
    )


def _reddit_stocks_compare(client: Any, args: Namespace) -> Any:
    return client.reddit.compare(_require_tickers(args), days=_with_default(args.days, 7))


def _reddit_stocks_market_sentiment(client: Any, args: Namespace) -> Any:
    return client.reddit.market_sentiment(days=_with_default(args.days, 1))


def _reddit_stocks_stats(client: Any, args: Namespace) -> Any:
    return client.reddit.stats()


def _reddit_stocks_health(client: Any, args: Namespace) -> Any:
    return client.reddit.health()


# --- News Stocks ---

def _news_stocks_trending(client: Any, args: Namespace) -> Any:
    return client.news.trending(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
        type=args.type,
        source=getattr(args, "source", None),
    )


def _news_stocks_trending_sectors(client: Any, args: Namespace) -> Any:
    return client.news.trending_sectors(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
        source=getattr(args, "source", None),
    )


def _news_stocks_trending_countries(client: Any, args: Namespace) -> Any:
    return client.news.trending_countries(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
        source=getattr(args, "source", None),
    )


def _news_stocks_stock(client: Any, args: Namespace) -> Any:
    return client.news.stock(
        _require_str(args, "ticker"),
        days=_with_default(args.days, 7),
    )


def _news_stocks_mentions(client: Any, args: Namespace) -> Any:
    return client.news.mentions(
        _require_str(args, "ticker"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 100),
    )


def _news_stocks_explain(client: Any, args: Namespace) -> Any:
    return client.news.explain(_require_str(args, "ticker"))


def _news_stocks_search(client: Any, args: Namespace) -> Any:
    return client.news.search(
        _require_str(args, "q", "query"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 20),
    )


def _news_stocks_compare(client: Any, args: Namespace) -> Any:
    return client.news.compare(
        _require_tickers(args),
        days=_with_default(args.days, 7),
    )


def _news_stocks_market_sentiment(client: Any, args: Namespace) -> Any:
    return client.news.market_sentiment(days=_with_default(args.days, 1))


def _news_stocks_stats(client: Any, args: Namespace) -> Any:
    return client.news.stats()


def _news_stocks_health(client: Any, args: Namespace) -> Any:
    return client.news.health()


# --- Reddit Crypto ---

def _reddit_crypto_trending(client: Any, args: Namespace) -> Any:
    return client.crypto.trending(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _reddit_crypto_token(client: Any, args: Namespace) -> Any:
    return client.crypto.token(_require_str(args, "symbol"), days=_with_default(args.days, 7))


def _reddit_crypto_mentions(client: Any, args: Namespace) -> Any:
    return client.crypto.mentions(
        _require_str(args, "symbol"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 100),
        include_inherited=bool(getattr(args, "include_inherited", False)),
    )


def _reddit_crypto_search(client: Any, args: Namespace) -> Any:
    return client.crypto.search(
        _require_str(args, "q", "query"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 20),
    )


def _reddit_crypto_compare(client: Any, args: Namespace) -> Any:
    return client.crypto.compare(_require_symbols(args), days=_with_default(args.days, 7))


def _reddit_crypto_market_sentiment(client: Any, args: Namespace) -> Any:
    return client.crypto.market_sentiment(days=_with_default(args.days, 1))


def _reddit_crypto_stats(client: Any, args: Namespace) -> Any:
    return client.crypto.stats()


def _reddit_crypto_health(client: Any, args: Namespace) -> Any:
    return client.crypto.health()


# --- X Stocks ---

def _x_stocks_trending(client: Any, args: Namespace) -> Any:
    return client.x.trending(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
        type=args.type,
    )


def _x_stocks_trending_sectors(client: Any, args: Namespace) -> Any:
    return client.x.trending_sectors(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _x_stocks_trending_countries(client: Any, args: Namespace) -> Any:
    return client.x.trending_countries(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _x_stocks_stock(client: Any, args: Namespace) -> Any:
    return client.x.stock(_require_str(args, "ticker"), days=_with_default(args.days, 7))


def _x_stocks_mentions(client: Any, args: Namespace) -> Any:
    return client.x.mentions(
        _require_str(args, "ticker"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 100),
    )


def _x_stocks_explain(client: Any, args: Namespace) -> Any:
    return client.x.explain(_require_str(args, "ticker"))


def _x_stocks_search(client: Any, args: Namespace) -> Any:
    return client.x.search(
        _require_str(args, "q", "query"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 20),
    )


def _x_stocks_compare(client: Any, args: Namespace) -> Any:
    return client.x.compare(_require_tickers(args), days=_with_default(args.days, 7))


def _x_stocks_market_sentiment(client: Any, args: Namespace) -> Any:
    return client.x.market_sentiment(days=_with_default(args.days, 1))


def _x_stocks_stats(client: Any, args: Namespace) -> Any:
    return client.x.stats()


def _x_stocks_health(client: Any, args: Namespace) -> Any:
    return client.x.health()


# --- Polymarket Stocks ---

def _polymarket_stocks_trending(client: Any, args: Namespace) -> Any:
    return client.polymarket.trending(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
        type=args.type,
    )


def _polymarket_stocks_trending_sectors(client: Any, args: Namespace) -> Any:
    return client.polymarket.trending_sectors(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _polymarket_stocks_trending_countries(client: Any, args: Namespace) -> Any:
    return client.polymarket.trending_countries(
        days=_with_default(args.days, 1),
        limit=_with_default(args.limit, 20),
        offset=_with_default(args.offset, 0),
    )


def _polymarket_stocks_stock(client: Any, args: Namespace) -> Any:
    return client.polymarket.stock(_require_str(args, "ticker"), days=_with_default(args.days, 7))


def _polymarket_stocks_mentions(client: Any, args: Namespace) -> Any:
    return client.polymarket.mentions(
        _require_str(args, "ticker"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 100),
    )


def _polymarket_stocks_search(client: Any, args: Namespace) -> Any:
    return client.polymarket.search(
        _require_str(args, "q", "query"),
        days=_with_default(args.days, 7),
        limit=_with_default(args.limit, 20),
    )


def _polymarket_stocks_compare(client: Any, args: Namespace) -> Any:
    return client.polymarket.compare(_require_tickers(args), days=_with_default(args.days, 7))


def _polymarket_stocks_market_sentiment(client: Any, args: Namespace) -> Any:
    return client.polymarket.market_sentiment(days=_with_default(args.days, 1))


def _polymarket_stocks_stats(client: Any, args: Namespace) -> Any:
    return client.polymarket.stats()


def _polymarket_stocks_health(client: Any, args: Namespace) -> Any:
    return client.polymarket.health()


ENDPOINTS: dict[str, EndpointSpec] = {
    # News Stocks
    "news-stocks.trending": EndpointSpec(
        "news-stocks.trending", "/news/stocks/v1/trending", "Trending News stocks", tuple(), ("days", "limit", "offset", "type", "source"), _news_stocks_trending
    ),
    "news-stocks.trending.sectors": EndpointSpec(
        "news-stocks.trending.sectors", "/news/stocks/v1/trending/sectors", "Trending News sectors", tuple(), ("days", "limit", "offset", "source"), _news_stocks_trending_sectors
    ),
    "news-stocks.trending.countries": EndpointSpec(
        "news-stocks.trending.countries", "/news/stocks/v1/trending/countries", "Trending News countries", tuple(), ("days", "limit", "offset", "source"), _news_stocks_trending_countries
    ),
    "news-stocks.stock": EndpointSpec(
        "news-stocks.stock", "/news/stocks/v1/stock/{ticker}", "Stock detail in News", ("ticker",), ("days",), _news_stocks_stock
    ),
    "news-stocks.stock.mentions": EndpointSpec(
        "news-stocks.stock.mentions", "/news/stocks/v1/stock/{ticker}/mentions", "Raw News mentions for a stock", ("ticker",), ("days", "limit"), _news_stocks_mentions
    ),
    "news-stocks.stock.explain": EndpointSpec(
        "news-stocks.stock.explain", "/news/stocks/v1/stock/{ticker}/explain", "AI explanation for News stock trend", ("ticker",), tuple(), _news_stocks_explain
    ),
    "news-stocks.search": EndpointSpec(
        "news-stocks.search",
        "/news/stocks/v1/search",
        "Search News stocks",
        ("q",),
        ("days", "limit"),
        _news_stocks_search,
    ),
    "news-stocks.compare": EndpointSpec(
        "news-stocks.compare", "/news/stocks/v1/compare", "Compare News stocks", ("tickers",), ("days",), _news_stocks_compare
    ),
    "news-stocks.market-sentiment": EndpointSpec(
        "news-stocks.market-sentiment", "/news/stocks/v1/market-sentiment", "Service-level News market sentiment", tuple(), ("days",), _news_stocks_market_sentiment
    ),
    "news-stocks.stats": EndpointSpec(
        "news-stocks.stats", "/news/stocks/v1/stats", "News stocks stats", tuple(), tuple(), _news_stocks_stats
    ),
    "news-stocks.health": EndpointSpec(
        "news-stocks.health", "/news/stocks/v1/health", "News stocks health", tuple(), tuple(), _news_stocks_health
    ),
    # Reddit Stocks
    "reddit-stocks.trending": EndpointSpec(
        "reddit-stocks.trending", "/reddit/stocks/v1/trending", "Trending Reddit stocks", tuple(), ("days", "limit", "offset", "type"), _reddit_stocks_trending
    ),
    "reddit-stocks.trending.sectors": EndpointSpec(
        "reddit-stocks.trending.sectors", "/reddit/stocks/v1/trending/sectors", "Trending Reddit sectors", tuple(), ("days", "limit", "offset"), _reddit_stocks_trending_sectors
    ),
    "reddit-stocks.trending.countries": EndpointSpec(
        "reddit-stocks.trending.countries", "/reddit/stocks/v1/trending/countries", "Trending Reddit countries", tuple(), ("days", "limit", "offset"), _reddit_stocks_trending_countries
    ),
    "reddit-stocks.stock": EndpointSpec(
        "reddit-stocks.stock", "/reddit/stocks/v1/stock/{ticker}", "Stock detail on Reddit", ("ticker",), ("days",), _reddit_stocks_stock
    ),
    "reddit-stocks.stock.mentions": EndpointSpec(
        "reddit-stocks.stock.mentions", "/reddit/stocks/v1/stock/{ticker}/mentions", "Raw Reddit mentions for a stock", ("ticker",), ("days", "limit", "include_inherited"), _reddit_stocks_mentions
    ),
    "reddit-stocks.stock.explain": EndpointSpec(
        "reddit-stocks.stock.explain", "/reddit/stocks/v1/stock/{ticker}/explain", "AI explanation for Reddit stock trend", ("ticker",), tuple(), _reddit_stocks_explain
    ),
    "reddit-stocks.search": EndpointSpec(
        "reddit-stocks.search",
        "/reddit/stocks/v1/search",
        "Search Reddit stocks",
        ("q",),
        ("days", "limit"),
        _reddit_stocks_search,
    ),
    "reddit-stocks.compare": EndpointSpec(
        "reddit-stocks.compare", "/reddit/stocks/v1/compare", "Compare Reddit stocks", ("tickers",), ("days",), _reddit_stocks_compare
    ),
    "reddit-stocks.market-sentiment": EndpointSpec(
        "reddit-stocks.market-sentiment", "/reddit/stocks/v1/market-sentiment", "Service-level Reddit market sentiment", tuple(), ("days",), _reddit_stocks_market_sentiment
    ),
    "reddit-stocks.stats": EndpointSpec(
        "reddit-stocks.stats", "/reddit/stocks/v1/stats", "Reddit stocks stats", tuple(), tuple(), _reddit_stocks_stats
    ),
    "reddit-stocks.health": EndpointSpec(
        "reddit-stocks.health", "/reddit/stocks/v1/health", "Reddit stocks health", tuple(), tuple(), _reddit_stocks_health
    ),
    # Reddit Crypto
    "reddit-crypto.trending": EndpointSpec(
        "reddit-crypto.trending", "/reddit/crypto/v1/trending", "Trending Reddit crypto tokens", tuple(), ("days", "limit", "offset"), _reddit_crypto_trending
    ),
    "reddit-crypto.token": EndpointSpec(
        "reddit-crypto.token", "/reddit/crypto/v1/token/{symbol}", "Crypto token detail on Reddit", ("symbol",), ("days",), _reddit_crypto_token
    ),
    "reddit-crypto.token.mentions": EndpointSpec(
        "reddit-crypto.token.mentions", "/reddit/crypto/v1/token/{symbol}/mentions", "Raw Reddit mentions for a crypto token", ("symbol",), ("days", "limit", "include_inherited"), _reddit_crypto_mentions
    ),
    "reddit-crypto.search": EndpointSpec(
        "reddit-crypto.search",
        "/reddit/crypto/v1/search",
        "Search Reddit crypto tokens",
        ("q",),
        ("days", "limit"),
        _reddit_crypto_search,
    ),
    "reddit-crypto.compare": EndpointSpec(
        "reddit-crypto.compare", "/reddit/crypto/v1/compare", "Compare Reddit crypto tokens", ("symbols",), ("days",), _reddit_crypto_compare
    ),
    "reddit-crypto.market-sentiment": EndpointSpec(
        "reddit-crypto.market-sentiment", "/reddit/crypto/v1/market-sentiment", "Service-level Reddit crypto market sentiment", tuple(), ("days",), _reddit_crypto_market_sentiment
    ),
    "reddit-crypto.stats": EndpointSpec(
        "reddit-crypto.stats", "/reddit/crypto/v1/stats", "Reddit crypto stats", tuple(), tuple(), _reddit_crypto_stats
    ),
    "reddit-crypto.health": EndpointSpec(
        "reddit-crypto.health", "/reddit/crypto/v1/health", "Reddit crypto health", tuple(), tuple(), _reddit_crypto_health
    ),
    # X Stocks
    "x-stocks.trending": EndpointSpec(
        "x-stocks.trending", "/x/stocks/v1/trending", "Trending X/Twitter stocks", tuple(), ("days", "limit", "offset", "type"), _x_stocks_trending
    ),
    "x-stocks.trending.sectors": EndpointSpec(
        "x-stocks.trending.sectors", "/x/stocks/v1/trending/sectors", "Trending X/Twitter sectors", tuple(), ("days", "limit", "offset"), _x_stocks_trending_sectors
    ),
    "x-stocks.trending.countries": EndpointSpec(
        "x-stocks.trending.countries", "/x/stocks/v1/trending/countries", "Trending X/Twitter countries", tuple(), ("days", "limit", "offset"), _x_stocks_trending_countries
    ),
    "x-stocks.stock": EndpointSpec(
        "x-stocks.stock", "/x/stocks/v1/stock/{ticker}", "Stock detail on X/Twitter", ("ticker",), ("days",), _x_stocks_stock
    ),
    "x-stocks.stock.mentions": EndpointSpec(
        "x-stocks.stock.mentions", "/x/stocks/v1/stock/{ticker}/mentions", "Raw X/Twitter mentions for a stock", ("ticker",), ("days", "limit"), _x_stocks_mentions
    ),
    "x-stocks.stock.explain": EndpointSpec(
        "x-stocks.stock.explain", "/x/stocks/v1/stock/{ticker}/explain", "AI explanation for X/Twitter stock trend", ("ticker",), tuple(), _x_stocks_explain
    ),
    "x-stocks.search": EndpointSpec(
        "x-stocks.search",
        "/x/stocks/v1/search",
        "Search X/Twitter stocks",
        ("q",),
        ("days", "limit"),
        _x_stocks_search,
    ),
    "x-stocks.compare": EndpointSpec(
        "x-stocks.compare", "/x/stocks/v1/compare", "Compare X/Twitter stocks", ("tickers",), ("days",), _x_stocks_compare
    ),
    "x-stocks.market-sentiment": EndpointSpec(
        "x-stocks.market-sentiment", "/x/stocks/v1/market-sentiment", "Service-level X/Twitter market sentiment", tuple(), ("days",), _x_stocks_market_sentiment
    ),
    "x-stocks.stats": EndpointSpec(
        "x-stocks.stats", "/x/stocks/v1/stats", "X/Twitter stocks stats", tuple(), tuple(), _x_stocks_stats
    ),
    "x-stocks.health": EndpointSpec(
        "x-stocks.health", "/x/stocks/v1/health", "X/Twitter stocks health", tuple(), tuple(), _x_stocks_health
    ),
    # Polymarket Stocks
    "polymarket-stocks.trending": EndpointSpec(
        "polymarket-stocks.trending", "/polymarket/stocks/v1/trending", "Trending Polymarket stocks", tuple(), ("days", "limit", "offset", "type"), _polymarket_stocks_trending
    ),
    "polymarket-stocks.trending.sectors": EndpointSpec(
        "polymarket-stocks.trending.sectors", "/polymarket/stocks/v1/trending/sectors", "Trending Polymarket sectors", tuple(), ("days", "limit", "offset"), _polymarket_stocks_trending_sectors
    ),
    "polymarket-stocks.trending.countries": EndpointSpec(
        "polymarket-stocks.trending.countries", "/polymarket/stocks/v1/trending/countries", "Trending Polymarket countries", tuple(), ("days", "limit", "offset"), _polymarket_stocks_trending_countries
    ),
    "polymarket-stocks.stock": EndpointSpec(
        "polymarket-stocks.stock", "/polymarket/stocks/v1/stock/{ticker}", "Stock detail on Polymarket", ("ticker",), ("days",), _polymarket_stocks_stock
    ),
    "polymarket-stocks.stock.mentions": EndpointSpec(
        "polymarket-stocks.stock.mentions", "/polymarket/stocks/v1/stock/{ticker}/mentions", "Raw Polymarket mentions for a stock", ("ticker",), ("days", "limit"), _polymarket_stocks_mentions
    ),
    "polymarket-stocks.search": EndpointSpec(
        "polymarket-stocks.search",
        "/polymarket/stocks/v1/search",
        "Search Polymarket stocks",
        ("q",),
        ("days", "limit"),
        _polymarket_stocks_search,
    ),
    "polymarket-stocks.compare": EndpointSpec(
        "polymarket-stocks.compare", "/polymarket/stocks/v1/compare", "Compare Polymarket stocks", ("tickers",), ("days",), _polymarket_stocks_compare
    ),
    "polymarket-stocks.market-sentiment": EndpointSpec(
        "polymarket-stocks.market-sentiment", "/polymarket/stocks/v1/market-sentiment", "Service-level Polymarket market sentiment", tuple(), ("days",), _polymarket_stocks_market_sentiment
    ),
    "polymarket-stocks.stats": EndpointSpec(
        "polymarket-stocks.stats", "/polymarket/stocks/v1/stats", "Polymarket stocks stats", tuple(), tuple(), _polymarket_stocks_stats
    ),
    "polymarket-stocks.health": EndpointSpec(
        "polymarket-stocks.health", "/polymarket/stocks/v1/health", "Polymarket stocks health", tuple(), tuple(), _polymarket_stocks_health
    ),
}


def list_endpoints() -> list[EndpointSpec]:
    return sorted(ENDPOINTS.values(), key=lambda spec: spec.endpoint_id)


def invoke_endpoint(client: Any, endpoint_id: str, args: Namespace) -> Any:
    spec = ENDPOINTS.get(endpoint_id)
    if spec is None:
        valid = ", ".join(sorted(ENDPOINTS.keys()))
        raise CliUsageError(f"Unknown endpoint id: {endpoint_id}. Valid ids: {valid}")
    if getattr(args, "source", None) and "source" not in spec.required_params and "source" not in spec.optional_params:
        raise CliUsageError(f"Endpoint {endpoint_id} does not support --source")
    return spec.invoke(client, args)


def endpoint_paths() -> set[str]:
    return {spec.path for spec in ENDPOINTS.values()}


def is_health_endpoint(endpoint_id: str) -> bool:
    return endpoint_id.endswith(".health")
