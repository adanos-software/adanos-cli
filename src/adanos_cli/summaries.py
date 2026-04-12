"""High-level reporting helpers for human-friendly CLI output."""

from __future__ import annotations

from typing import Any

from .utils import fmt_num, short_error, to_plain


def _extract_api_error(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    detail = data.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if isinstance(detail, dict):
        detail_message = detail.get("message") or detail.get("error")
        if isinstance(detail_message, str) and detail_message.strip():
            return detail_message.strip()
        return "API request failed"

    error = data.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    return None


def _call_safe(fn) -> dict[str, Any]:
    try:
        data = to_plain(fn())
        api_error = _extract_api_error(data)
        if api_error:
            return {"ok": False, "error": api_error, "data": data}
        return {"ok": True, "data": data}
    except Exception as exc:  # pragma: no cover - thin safety net
        return {"ok": False, "error": short_error(exc)}


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _resolve_volume_value(data: dict[str, Any], volume_key: str) -> Any:
    value = data.get(volume_key)
    if value is None and volume_key == "mentions":
        return data.get("total_mentions")
    return value


def _derive_signal(sentiment: float | None, *, buzz: float | None, platforms: int) -> str:
    if sentiment is None:
        if (buzz or 0) >= 85 and platforms >= 2:
            return "hot"
        return "neutral"
    if sentiment >= 0.12:
        return "bullish"
    if sentiment <= -0.12:
        return "bearish"
    return "neutral"


def _derive_confidence(
    *,
    platforms: int,
    volume: float,
    buzz: float | None,
    sentiment: float | None,
) -> int:
    score = 0.0
    score += min(float(max(platforms, 1)) * 18.0, 45.0)
    score += min(max(volume, 0.0) / 20.0, 25.0)
    if buzz is not None:
        score += min(max((buzz - 40.0) * 0.5, 0.0), 20.0)
    if sentiment is not None:
        score += min(abs(sentiment) * 100.0, 15.0)
    score = max(0.0, min(score, 99.0))
    return int(round(score))


def _top_signal_rows(
    rows: list[dict[str, Any]],
    *,
    signal: str,
    symbol_key: str,
    sentiment_key: str,
    top: int = 3,
) -> list[dict[str, Any]]:
    selected = [row for row in rows if row.get("signal") == signal]
    selected.sort(
        key=lambda row: (
            int(row.get("confidence") or 0),
            float(row.get("consensus_buzz", row.get("buzz_score")) or 0),
            abs(float(row.get(sentiment_key) or 0)),
        ),
        reverse=True,
    )
    compact: list[dict[str, Any]] = []
    for row in selected[:top]:
        compact.append(
            {
                "asset": row.get(symbol_key),
                "signal": row.get("signal"),
                "confidence": row.get("confidence"),
                "buzz": row.get("consensus_buzz", row.get("buzz_score")),
                "sentiment": row.get(sentiment_key),
            }
        )
    return compact


def build_stock_report(client: Any, ticker: str, *, days: int) -> dict[str, Any]:
    symbol = ticker.upper().replace("$", "")
    return {
        "kind": "stock_report",
        "ticker": symbol,
        "days": days,
        "news": _call_safe(lambda: client.news.stock(symbol, days=days)),
        "reddit": _call_safe(lambda: client.reddit.stock(symbol, days=days)),
        "x": _call_safe(lambda: client.x.stock(symbol, days=days)),
        "polymarket": _call_safe(lambda: client.polymarket.stock(symbol, days=days)),
        "reddit_explain": _call_safe(lambda: client.reddit.explain(symbol)),
        "x_explain": _call_safe(lambda: client.x.explain(symbol)),
    }


def build_crypto_report(client: Any, symbol: str, *, days: int) -> dict[str, Any]:
    token = symbol.upper().replace("$", "")
    return {
        "kind": "crypto_report",
        "symbol": token,
        "days": days,
        "reddit_crypto": _call_safe(lambda: client.crypto.token(token, days=days)),
        "search": _call_safe(lambda: client.crypto.search(token)),
        "stats": _call_safe(lambda: client.crypto.stats()),
    }


def build_crypto_compare_report(client: Any, symbols: list[str], *, days: int) -> dict[str, Any]:
    normalized = [s.upper().replace("$", "") for s in symbols if s.strip()]
    return {
        "kind": "crypto_compare",
        "symbols": normalized,
        "days": days,
        "reddit_crypto_compare": _call_safe(lambda: client.crypto.compare(normalized, days=days)),
    }


def build_stock_compare_report(client: Any, tickers: list[str], *, days: int) -> dict[str, Any]:
    normalized = [s.upper().replace("$", "") for s in tickers if s.strip()]
    return {
        "kind": "stock_compare",
        "tickers": normalized,
        "days": days,
        "news": _call_safe(lambda: client.news.compare(normalized, days=days)),
        "reddit": _call_safe(lambda: client.reddit.compare(normalized, days=days)),
        "x": _call_safe(lambda: client.x.compare(normalized, days=days)),
        "polymarket": _call_safe(lambda: client.polymarket.compare(normalized, days=days)),
    }


def build_trending_report(client: Any, *, asset: str, days: int, limit: int = 5) -> dict[str, Any]:
    if asset == "crypto":
        return {
            "kind": "trending_report",
            "asset": "crypto",
            "days": days,
            "reddit_crypto": _call_safe(lambda: client.crypto.trending(days=days, limit=limit, offset=0)),
        }

    return {
        "kind": "trending_report",
        "asset": "stocks",
        "days": days,
        "news": _call_safe(lambda: client.news.trending(days=days, limit=limit, offset=0)),
        "reddit": _call_safe(lambda: client.reddit.trending(days=days, limit=limit, offset=0)),
        "x": _call_safe(lambda: client.x.trending(days=days, limit=limit, offset=0)),
        "polymarket": _call_safe(lambda: client.polymarket.trending(days=days, limit=limit, offset=0)),
    }


def _extract_list_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload.get("ok"):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def build_stock_scan_report(client: Any, *, days: int, limit: int) -> dict[str, Any]:
    sources = {
        "news": _call_safe(lambda: client.news.trending(days=days, limit=limit, offset=0)),
        "reddit": _call_safe(lambda: client.reddit.trending(days=days, limit=limit, offset=0)),
        "x": _call_safe(lambda: client.x.trending(days=days, limit=limit, offset=0)),
        "polymarket": _call_safe(lambda: client.polymarket.trending(days=days, limit=limit, offset=0)),
    }

    combined: dict[str, dict[str, Any]] = {}
    for source, payload in sources.items():
        for row in _extract_list_rows(payload):
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            entry = combined.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "company_name": row.get("company_name"),
                    "platforms": 0,
                    "total_volume": 0.0,
                    "buzz_sum": 0.0,
                    "buzz_count": 0,
                    "sentiment_sum": 0.0,
                    "sentiment_count": 0,
                    "sources": {},
                },
            )
            buzz = row.get("buzz_score")
            volume = row.get("mentions", row.get("trade_count", 0))
            sentiment = row.get("sentiment_score", row.get("sentiment"))

            entry["platforms"] += 1
            if isinstance(volume, (int, float)):
                entry["total_volume"] += float(volume)
            if isinstance(buzz, (int, float)):
                entry["buzz_sum"] += float(buzz)
                entry["buzz_count"] += 1
            if isinstance(sentiment, (int, float)):
                entry["sentiment_sum"] += float(sentiment)
                entry["sentiment_count"] += 1
            entry["sources"][source] = {
                "buzz_score": buzz,
                "volume": volume,
                "sentiment": sentiment,
            }

    rows: list[dict[str, Any]] = []
    for entry in combined.values():
        buzz_count = int(entry.get("buzz_count") or 0)
        sentiment_count = int(entry.get("sentiment_count") or 0)
        consensus_buzz = (entry["buzz_sum"] / buzz_count) if buzz_count else None
        consensus_sentiment = (entry["sentiment_sum"] / sentiment_count) if sentiment_count else None
        platforms = int(entry.get("platforms") or 0)
        total_volume = float(entry.get("total_volume") or 0)
        signal = _derive_signal(consensus_sentiment, buzz=consensus_buzz, platforms=platforms)
        confidence = _derive_confidence(
            platforms=platforms,
            volume=total_volume,
            buzz=consensus_buzz,
            sentiment=consensus_sentiment,
        )
        rows.append(
            {
                "ticker": entry["ticker"],
                "company_name": entry.get("company_name"),
                "platforms": platforms,
                "consensus_buzz": consensus_buzz,
                "consensus_sentiment": consensus_sentiment,
                "signal": signal,
                "confidence": confidence,
                "total_volume": int(total_volume),
                "sources": entry.get("sources", {}),
            }
        )

    rows.sort(
        key=lambda row: (
            int(row.get("confidence") or 0),
            float(row.get("consensus_buzz") or 0),
            int(row.get("platforms") or 0),
            int(row.get("total_volume") or 0),
        ),
        reverse=True,
    )

    return {
        "kind": "stock_scan",
        "days": days,
        "limit": limit,
        "rows": rows,
        "source_status": {name: {"ok": payload.get("ok"), "error": payload.get("error")} for name, payload in sources.items()},
    }


def build_crypto_scan_report(client: Any, *, days: int, limit: int) -> dict[str, Any]:
    payload = _call_safe(lambda: client.crypto.trending(days=days, limit=limit, offset=0))
    rows = _extract_list_rows(payload)
    normalized_rows = []
    for row in rows:
        buzz = _as_float(row.get("buzz_score"))
        mentions = int(row.get("mentions") or 0)
        sentiment = _as_float(row.get("sentiment_score"))
        signal = _derive_signal(sentiment, buzz=buzz, platforms=1)
        confidence = _derive_confidence(
            platforms=1,
            volume=float(mentions),
            buzz=buzz,
            sentiment=sentiment,
        )
        normalized_rows.append(
            {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "buzz_score": buzz,
                "mentions": mentions,
                "sentiment": sentiment,
                "upvotes": row.get("total_upvotes"),
                "signal": signal,
                "confidence": confidence,
            }
        )
    normalized_rows.sort(
        key=lambda row: (
            int(row.get("confidence") or 0),
            float(row.get("buzz_score") or 0),
            int(row.get("mentions") or 0),
        ),
        reverse=True,
    )
    return {
        "kind": "crypto_scan",
        "days": days,
        "limit": limit,
        "rows": normalized_rows,
        "source_status": {"reddit_crypto": {"ok": payload.get("ok"), "error": payload.get("error")}},
    }


def build_market_briefing_report(
    client: Any,
    *,
    profile: str,
    days: int,
    limit: int,
    stock_focus: list[str] | None = None,
    crypto_focus: list[str] | None = None,
) -> dict[str, Any]:
    profile_normalized = profile.lower().strip()
    report: dict[str, Any] = {
        "kind": "briefing",
        "profile": profile_normalized,
        "days": days,
        "limit": limit,
    }

    include_stocks = profile_normalized in {"starter", "daytrader", "swing", "investor", "research", "portfolio"}
    include_crypto = profile_normalized in {"starter", "daytrader", "swing", "crypto", "research", "portfolio"}

    if include_stocks:
        stocks_scan = build_stock_scan_report(client, days=days, limit=limit)
        rows = [row for row in stocks_scan.get("rows", []) if isinstance(row, dict)]
        if profile_normalized in {"daytrader", "investor"}:
            rows = [row for row in rows if (row.get("platforms") or 0) >= 2]
        if profile_normalized == "research":
            rows = [row for row in rows if (row.get("confidence") or 0) >= 45]
        stocks_scan["rows"] = rows
        report["stocks_scan"] = stocks_scan
    if include_crypto:
        crypto_scan = build_crypto_scan_report(client, days=days, limit=limit)
        rows = [row for row in crypto_scan.get("rows", []) if isinstance(row, dict)]
        if profile_normalized == "daytrader":
            rows = [row for row in rows if (row.get("mentions") or 0) >= 50]
        if profile_normalized == "research":
            rows = [row for row in rows if (row.get("confidence") or 0) >= 30]
        crypto_scan["rows"] = rows
        report["crypto_scan"] = crypto_scan

    if profile_normalized in {"investor", "research", "portfolio"}:
        report["reddit_sectors"] = _call_safe(lambda: client.reddit.trending_sectors(days=days, limit=5, offset=0))
        report["reddit_countries"] = _call_safe(lambda: client.reddit.trending_countries(days=days, limit=5, offset=0))

    if stock_focus:
        report["stock_focus"] = build_stock_compare_report(client, stock_focus, days=days)
    if crypto_focus:
        report["crypto_focus"] = build_crypto_compare_report(client, crypto_focus, days=days)

    stock_rows = []
    crypto_rows = []
    if isinstance(report.get("stocks_scan"), dict):
        stock_rows = [row for row in report["stocks_scan"].get("rows", []) if isinstance(row, dict)]
    if isinstance(report.get("crypto_scan"), dict):
        crypto_rows = [row for row in report["crypto_scan"].get("rows", []) if isinstance(row, dict)]

    playbook: dict[str, Any] = {}
    if stock_rows:
        playbook["stocks"] = {
            "long_candidates": _top_signal_rows(
                stock_rows,
                signal="bullish",
                symbol_key="ticker",
                sentiment_key="consensus_sentiment",
                top=3,
            ),
            "short_watch": _top_signal_rows(
                stock_rows,
                signal="bearish",
                symbol_key="ticker",
                sentiment_key="consensus_sentiment",
                top=3,
            ),
        }
    if crypto_rows:
        playbook["crypto"] = {
            "long_candidates": _top_signal_rows(
                crypto_rows,
                signal="bullish",
                symbol_key="symbol",
                sentiment_key="sentiment",
                top=3,
            ),
            "short_watch": _top_signal_rows(
                crypto_rows,
                signal="bearish",
                symbol_key="symbol",
                sentiment_key="sentiment",
                top=3,
            ),
        }
    if playbook:
        report["playbook"] = playbook

    return report


def build_search_fallback_report(client: Any, query: str) -> dict[str, Any]:
    return {
        "kind": "search_fallback",
        "query": query,
        "news_stocks": _call_safe(lambda: client.news.search(query, days=7, limit=10)),
        "reddit_stocks": _call_safe(lambda: client.reddit.search(query, days=7, limit=10)),
        "x_stocks": _call_safe(lambda: client.x.search(query, days=7, limit=10)),
        "polymarket_stocks": _call_safe(lambda: client.polymarket.search(query, days=7, limit=10)),
        "reddit_crypto": _call_safe(lambda: client.crypto.search(query, days=7, limit=10)),
    }


def _format_source(name: str, payload: dict[str, Any], *, mentions_key: str, sentiment_key: str = "sentiment_score") -> str:
    if not payload.get("ok"):
        return f"- {name}: unavailable ({payload.get('error', 'request failed')})"

    data = payload.get("data")
    if not isinstance(data, dict):
        return f"- {name}: no structured data"

    if data.get("found") is False:
        return f"- {name}: no data in selected window"

    buzz = fmt_num(data.get("buzz_score"))
    trend = data.get("trend") or "n/a"
    mentions = fmt_num(_resolve_volume_value(data, mentions_key))
    sentiment = fmt_num(data.get(sentiment_key))
    return f"- {name}: buzz={buzz}, trend={trend}, volume={mentions}, sentiment={sentiment}"


def format_stock_report(report: dict[str, Any]) -> str:
    lines = [
        f"Stock report for {report['ticker']} ({report['days']}d)",
        _format_source("News Stocks", report["news"], mentions_key="mentions"),
        _format_source("Reddit Stocks", report["reddit"], mentions_key="mentions"),
        _format_source("X/Twitter Stocks", report["x"], mentions_key="mentions"),
        _format_source("Polymarket Stocks", report["polymarket"], mentions_key="trade_count"),
    ]

    for key, label in (("reddit_explain", "Reddit Explain"), ("x_explain", "X/Twitter Explain")):
        explain = report.get(key, {})
        if explain.get("ok") and isinstance(explain.get("data"), dict):
            text = str(explain["data"].get("explanation") or "").strip()
            if text:
                lines.append(f"- {label}: " + text)
        elif not explain.get("ok"):
            lines.append(f"- {label}: unavailable ({explain.get('error', 'request failed')})")

    lines.append("Data sources covered: /news/stocks, /reddit/stocks, /x/stocks, /polymarket/stocks")
    return "\n".join(lines)


def format_crypto_report(report: dict[str, Any]) -> str:
    lines = [
        f"Crypto report for {report['symbol']} ({report['days']}d)",
        _format_source("Reddit Crypto", report["reddit_crypto"], mentions_key="mentions"),
    ]

    search_payload = report.get("search", {})
    if search_payload.get("ok") and isinstance(search_payload.get("data"), dict):
        lines.append(f"- Search matches: {search_payload['data'].get('count', 0)}")

    stats_payload = report.get("stats", {})
    if stats_payload.get("ok") and isinstance(stats_payload.get("data"), dict):
        lines.append(
            "- Dataset scope: "
            f"unique_tokens={fmt_num(stats_payload['data'].get('unique_tokens'))}, "
            f"supported_tokens={fmt_num(stats_payload['data'].get('supported_tokens'))}"
        )

    lines.append("Data source covered: /reddit/crypto")
    return "\n".join(lines)


def format_crypto_compare_report(report: dict[str, Any]) -> str:
    payload = report.get("reddit_crypto_compare", {})
    pair_label = ", ".join(report.get("symbols", []))
    if not payload.get("ok"):
        return f"Crypto compare for {pair_label} failed: {payload.get('error', 'request failed')}"

    data = payload.get("data")
    if not isinstance(data, dict):
        return f"Crypto compare for {pair_label}: no structured response"

    tokens = data.get("tokens") or []
    lines = [f"Crypto compare ({report['days']}d): {pair_label}"]
    for row in tokens:
        if not isinstance(row, dict):
            continue
        lines.append(
            "- "
            f"{row.get('symbol', 'n/a')}: buzz={fmt_num(row.get('buzz_score'))}, "
            f"mentions={fmt_num(row.get('mentions', row.get('total_mentions')))}, "
            f"sentiment={fmt_num(row.get('sentiment', row.get('sentiment_score')))}, "
            f"upvotes={fmt_num(row.get('upvotes', row.get('total_upvotes')))}"
        )
    if len(lines) == 1:
        lines.append("- no rows returned")
    return "\n".join(lines)


def format_stock_compare_report(report: dict[str, Any]) -> str:
    def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not payload.get("ok"):
            return []
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        rows = data.get("stocks")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    lines = [f"Stock compare ({report['days']}d): {', '.join(report.get('tickers', []))}"]
    for key, label in (("news", "News"), ("reddit", "Reddit"), ("x", "X/Twitter"), ("polymarket", "Polymarket")):
        payload = report.get(key, {})
        if not payload.get("ok"):
            lines.append(f"- {label}: unavailable ({payload.get('error', 'request failed')})")
            continue
        rows = _rows(payload)
        if not rows:
            lines.append(f"- {label}: no rows returned")
            continue
        lines.append(f"- {label}:")
        for row in rows[:10]:
            mentions = row.get("mentions", row.get("trade_count"))
            sentiment = row.get("sentiment", row.get("sentiment_score"))
            lines.append(
                "  "
                f"{row.get('ticker', 'n/a')}: buzz={fmt_num(row.get('buzz_score'))}, "
                f"volume={fmt_num(mentions)}, sentiment={fmt_num(sentiment)}"
            )
    return "\n".join(lines)


def format_trending_report(report: dict[str, Any]) -> str:
    def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not payload.get("ok"):
            return []
        data = payload.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    asset = report.get("asset", "stocks")
    days = report.get("days", "n/a")
    if asset == "crypto":
        payload = report.get("reddit_crypto", {})
        if not payload.get("ok"):
            return f"Trending crypto ({days}d): unavailable ({payload.get('error', 'request failed')})"
        rows = _extract_rows(payload)
        lines = [f"Trending crypto ({days}d):"]
        for row in rows[:5]:
            lines.append(
                "- "
                f"{row.get('symbol', 'n/a')}: buzz={fmt_num(row.get('buzz_score'))}, "
                f"mentions={fmt_num(row.get('mentions'))}, sentiment={fmt_num(row.get('sentiment_score'))}"
            )
        if len(lines) == 1:
            lines.append("- no rows returned")
        return "\n".join(lines)

    lines = [f"Trending stocks ({days}d):"]
    for key, label in (("news", "News"), ("reddit", "Reddit"), ("x", "X/Twitter"), ("polymarket", "Polymarket")):
        payload = report.get(key, {})
        if not payload.get("ok"):
            lines.append(f"- {label}: unavailable ({payload.get('error', 'request failed')})")
            continue
        rows = _extract_rows(payload)
        if not rows:
            lines.append(f"- {label}: no rows returned")
            continue
        top = rows[:5]
        joined = ", ".join(
            f"{row.get('ticker', 'n/a')}({fmt_num(row.get('buzz_score'))})" for row in top
        )
        lines.append(f"- {label}: {joined}")
    return "\n".join(lines)


def format_stock_scan_report(report: dict[str, Any], *, top: int = 10) -> str:
    rows = [row for row in (report.get("rows") or []) if isinstance(row, dict)]
    lines = [f"Stock scan ({report.get('days', 'n/a')}d):"]
    if report.get("style"):
        lines.append(f"- style: {report.get('style')}")
    if not rows:
        lines.append("- no rows returned")
    for row in rows[:top]:
        sources = row.get("sources") or {}
        parts = []
        for key, short in (("news", "N"), ("reddit", "R"), ("x", "X"), ("polymarket", "P")):
            source = sources.get(key)
            if not isinstance(source, dict):
                continue
            parts.append(f"{short}:{fmt_num(source.get('buzz_score'))}")
        source_label = " ".join(parts) if parts else "n/a"
        lines.append(
            "- "
            f"{row.get('ticker', 'n/a')}: consensus={fmt_num(row.get('consensus_buzz'))}, "
            f"sentiment={fmt_num(row.get('consensus_sentiment'))}, signal={row.get('signal', 'n/a')} "
            f"({fmt_num(row.get('confidence'))}), platforms={fmt_num(row.get('platforms'))}, "
            f"volume={fmt_num(row.get('total_volume'))}, {source_label}"
        )
    source_status = report.get("source_status") or {}
    for source, status in source_status.items():
        if isinstance(status, dict) and not status.get("ok"):
            lines.append(f"- source {source}: unavailable ({status.get('error', 'request failed')})")
    return "\n".join(lines)


def format_crypto_scan_report(report: dict[str, Any], *, top: int = 10) -> str:
    rows = [row for row in (report.get("rows") or []) if isinstance(row, dict)]
    lines = [f"Crypto scan ({report.get('days', 'n/a')}d):"]
    if report.get("style"):
        lines.append(f"- style: {report.get('style')}")
    if not rows:
        lines.append("- no rows returned")
    for row in rows[:top]:
        lines.append(
            "- "
            f"{row.get('symbol', 'n/a')}: buzz={fmt_num(row.get('buzz_score'))}, "
            f"mentions={fmt_num(row.get('mentions'))}, sentiment={fmt_num(row.get('sentiment'))}, "
            f"signal={row.get('signal', 'n/a')} ({fmt_num(row.get('confidence'))}), "
            f"upvotes={fmt_num(row.get('upvotes'))}"
        )
    source_status = report.get("source_status") or {}
    status = source_status.get("reddit_crypto")
    if isinstance(status, dict) and not status.get("ok"):
        lines.append(f"- source reddit_crypto: unavailable ({status.get('error', 'request failed')})")
    return "\n".join(lines)


def format_market_briefing_report(report: dict[str, Any]) -> str:
    profile = str(report.get("profile") or "starter")
    days = report.get("days", "n/a")
    lines = [f"Market briefing ({profile}, {days}d)"]

    stock_scan = report.get("stocks_scan")
    if isinstance(stock_scan, dict):
        lines.append("")
        lines.append(format_stock_scan_report(stock_scan, top=5))

    crypto_scan = report.get("crypto_scan")
    if isinstance(crypto_scan, dict):
        lines.append("")
        lines.append(format_crypto_scan_report(crypto_scan, top=5))

    stock_focus = report.get("stock_focus")
    if isinstance(stock_focus, dict):
        lines.append("")
        lines.append(format_stock_compare_report(stock_focus))

    crypto_focus = report.get("crypto_focus")
    if isinstance(crypto_focus, dict):
        lines.append("")
        lines.append(format_crypto_compare_report(crypto_focus))

    if profile in {"investor", "research", "portfolio"}:
        sectors_payload = report.get("reddit_sectors", {})
        if isinstance(sectors_payload, dict) and sectors_payload.get("ok"):
            rows = sectors_payload.get("data")
            if isinstance(rows, list):
                names = [str(row.get("sector")) for row in rows[:5] if isinstance(row, dict)]
                if names:
                    lines.append("")
                    lines.append("Top Reddit sectors: " + ", ".join(names))

        countries_payload = report.get("reddit_countries", {})
        if isinstance(countries_payload, dict) and countries_payload.get("ok"):
            rows = countries_payload.get("data")
            if isinstance(rows, list):
                names = [str(row.get("country")) for row in rows[:5] if isinstance(row, dict)]
                if names:
                    lines.append("Top Reddit countries: " + ", ".join(names))

    playbook = report.get("playbook")
    if isinstance(playbook, dict):
        lines.append("")
        lines.append("Playbook:")
        for asset_key, asset_payload in (("stocks", playbook.get("stocks")), ("crypto", playbook.get("crypto"))):
            if not isinstance(asset_payload, dict):
                continue
            long_rows = [row for row in asset_payload.get("long_candidates", []) if isinstance(row, dict)]
            short_rows = [row for row in asset_payload.get("short_watch", []) if isinstance(row, dict)]
            if long_rows:
                joined = ", ".join(
                    f"{row.get('asset')}[{row.get('signal')}/{fmt_num(row.get('confidence'))}]"
                    for row in long_rows
                )
                lines.append(f"- {asset_key} longs: {joined}")
            if short_rows:
                joined = ", ".join(
                    f"{row.get('asset')}[{row.get('signal')}/{fmt_num(row.get('confidence'))}]"
                    for row in short_rows
                )
                lines.append(f"- {asset_key} short-watch: {joined}")

    return "\n".join(lines)


def format_search_fallback_report(report: dict[str, Any]) -> str:
    lines = [f"No clear ticker/symbol intent found. Showing search snapshot for: {report['query']}"]
    for key, label in (
        ("news_stocks", "News Stocks"),
        ("reddit_stocks", "Reddit Stocks"),
        ("x_stocks", "X/Twitter Stocks"),
        ("polymarket_stocks", "Polymarket Stocks"),
        ("reddit_crypto", "Reddit Crypto"),
    ):
        payload = report.get(key, {})
        if not payload.get("ok"):
            lines.append(f"- {label}: unavailable ({payload.get('error', 'request failed')})")
            continue
        data = payload.get("data")
        if not isinstance(data, dict):
            lines.append(f"- {label}: no structured data")
            continue
        lines.append(f"- {label}: {data.get('count', 0)} matches")
    return "\n".join(lines)
