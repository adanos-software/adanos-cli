"""Lightweight natural-language intent parsing for `adanos ask`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_STOPWORDS = {
    "THE", "AND", "WITH", "FOR", "HOW", "DO", "DOES", "LOOK", "LOOKS", "WHAT", "PLEASE",
    "MANY", "USER", "USERS", "ABOUT", "TALK", "TALKING", "SHOW", "ME",
    "MENTION", "MENTIONED",
    "TOP", "TRENDING", "TREND", "TODAY", "MOST", "MENTIONED", "MENTIONS",
    "LIST", "LEADERBOARD", "RANKING", "RANK",
    "STOCK", "TICKER", "CRYPTO", "COIN", "TOKEN",
    "WATCHLIST", "PORTFOLIO", "BRIEFING", "REPORT", "OVERVIEW", "SUMMARY",
    "SCAN", "SCANNER", "SCREENER", "SIGNAL", "SIGNALS", "MARKET",
    "PROFILE", "SETUP", "SETUPS", "FROM", "FOR",
    "COMPARE", "TO", "VERSUS",
    "STARTER", "DAYTRADER", "SWING", "INVESTOR", "RESEARCH",
}

_PAIR_RE = re.compile(r"\b([A-Za-z0-9]{2,20})\s*/\s*([A-Za-z0-9]{2,20})\b")
_VS_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9]{1,19})\s*(?:vs|versus)\s*([A-Za-z][A-Za-z0-9]{1,19})\b", re.IGNORECASE)
_COMPARE_AND_RE = re.compile(
    r"\bcompare\s+([A-Za-z][A-Za-z0-9]{1,19})\s+(?:and|with|to)\s+([A-Za-z][A-Za-z0-9]{1,19})\b",
    re.IGNORECASE,
)
_PREF_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,19})\b")
_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9]{1,19})\b")
_WATCHLIST_RE = re.compile(r"\b(?:watchlist|portfolio)\s+([A-Za-z0-9_-]{1,40})\b", re.IGNORECASE)
_COMMON_CRYPTO_SYMBOLS = {
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "USDT", "USDC", "AVAX", "TRX", "DOT", "LINK", "MATIC",
}
_CRYPTO_NAME_TO_SYMBOL = {
    "BITCOIN": "BTC",
    "ETHEREUM": "ETH",
    "SOLANA": "SOL",
    "RIPPLE": "XRP",
    "CARDANO": "ADA",
    "DOGECOIN": "DOGE",
    "BINANCE": "BNB",
    "AVALANCHE": "AVAX",
    "POLKADOT": "DOT",
    "CHAINLINK": "LINK",
    "POLYGON": "MATIC",
}


@dataclass(frozen=True)
class AskIntent:
    kind: Literal[
        "stock_report",
        "stock_compare",
        "crypto_report",
        "crypto_compare",
        "trending_report",
        "scan_report",
        "briefing_report",
        "watchlist_report",
        "search_fallback",
    ]
    primary: str | None = None
    secondary: str | None = None
    assets: tuple[str, ...] = ()


def _extract_prefixed(text: str) -> list[str]:
    return [m.group(1).upper() for m in _PREF_RE.finditer(text)]


def _extract_tokens(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for m in _TOKEN_RE.finditer(text):
        token = m.group(1).upper()
        if token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        candidates.append(token)
    return candidates


def _pick_stock_candidate(text: str) -> str | None:
    pref = _extract_prefixed(text)
    if pref:
        token = pref[0]
        if 1 <= len(token) <= 10:
            return token

    for token in _extract_tokens(text):
        if 1 <= len(token) <= 10:
            return token
    return None


def _pick_crypto_candidate(text: str) -> str | None:
    pref = _extract_prefixed(text)
    if pref:
        token = pref[0]
        if 2 <= len(token) <= 20:
            return token

    for token in _extract_tokens(text):
        mapped = _CRYPTO_NAME_TO_SYMBOL.get(token)
        if mapped:
            return mapped
        if 2 <= len(token) <= 20:
            return token
    return None


def _pick_briefing_profile(lower: str) -> str:
    if "daytrader" in lower or "day trader" in lower:
        return "daytrader"
    if "swing" in lower:
        return "swing"
    if "investor" in lower or "long term" in lower:
        return "investor"
    if "crypto" in lower:
        return "crypto"
    if "research" in lower or "analyst" in lower:
        return "research"
    if "portfolio" in lower:
        return "portfolio"
    return "starter"


def _is_common_crypto_symbol(symbol: str) -> bool:
    return symbol.upper().replace("$", "") in _COMMON_CRYPTO_SYMBOLS


def is_common_crypto_symbol(symbol: str) -> bool:
    """Return whether a symbol is unambiguously recognized as common crypto."""
    return _is_common_crypto_symbol(symbol)


def _canonical_crypto_symbol(token: str) -> str:
    normalized = token.upper().replace("$", "")
    return _CRYPTO_NAME_TO_SYMBOL.get(normalized, normalized)


def parse_ask_intent(text: str) -> AskIntent:
    raw = text.strip()
    lower = raw.lower()
    has_crypto_words = "crypto" in lower or "coin" in lower or "token" in lower
    has_stock_words = "stock" in lower or "ticker" in lower
    has_trending_words = any(
        token in lower
        for token in (
            "trending",
            "trend",
            "top",
            "most mentioned",
            "leaderboard",
            "ranking",
            "today",
        )
    )
    has_scan_words = any(token in lower for token in ("scan", "scanner", "screener", "find setups", "setup"))
    has_briefing_words = any(token in lower for token in ("briefing", "overview", "summary"))
    has_watchlist_words = "watchlist" in lower or "portfolio" in lower

    pair = _PAIR_RE.search(raw)
    if pair and has_crypto_words:
        return AskIntent("crypto_compare", pair.group(1).upper(), pair.group(2).upper())
    if pair and has_stock_words:
        return AskIntent("stock_compare", pair.group(1).upper(), pair.group(2).upper())

    vs_pair = _VS_RE.search(raw)
    if vs_pair and has_crypto_words:
        return AskIntent("crypto_compare", vs_pair.group(1).upper(), vs_pair.group(2).upper())
    if vs_pair:
        left = vs_pair.group(1).upper()
        right = vs_pair.group(2).upper()
        if left in _COMMON_CRYPTO_SYMBOLS and right in _COMMON_CRYPTO_SYMBOLS:
            return AskIntent("crypto_compare", left, right)
        return AskIntent("stock_compare", left, right)

    compare_pair = _COMPARE_AND_RE.search(raw)
    if compare_pair:
        left = compare_pair.group(1).upper()
        right = compare_pair.group(2).upper()
        crypto_left = _canonical_crypto_symbol(left)
        crypto_right = _canonical_crypto_symbol(right)
        if has_crypto_words or (_is_common_crypto_symbol(crypto_left) and _is_common_crypto_symbol(crypto_right)):
            return AskIntent("crypto_compare", crypto_left, crypto_right)
        return AskIntent("stock_compare", left, right)

    if re.search(r"\bcompare\b", raw, re.IGNORECASE):
        compare_text = re.split(r"\bcompare\b", raw, maxsplit=1, flags=re.IGNORECASE)[1]
        candidates = [token for token in _extract_tokens(compare_text) if 1 <= len(token) <= 10]
        if len(candidates) >= 2:
            if len(candidates) == 2 and (
                has_crypto_words or all(_is_common_crypto_symbol(token) for token in candidates)
            ):
                return AskIntent(
                    "crypto_compare",
                    _canonical_crypto_symbol(candidates[0]),
                    _canonical_crypto_symbol(candidates[1]),
                )
            assets = tuple(candidates[:10])
            return AskIntent("stock_compare", assets[0], assets[1], assets)

    if has_trending_words and has_crypto_words:
        return AskIntent("trending_report", "crypto")
    if has_trending_words:
        return AskIntent("trending_report", "stocks")

    if has_briefing_words:
        profile = _pick_briefing_profile(lower)
        return AskIntent("briefing_report", profile)

    if has_scan_words:
        if has_crypto_words and has_stock_words:
            return AskIntent("scan_report", "all")
        if has_crypto_words:
            return AskIntent("scan_report", "crypto")
        if has_stock_words:
            return AskIntent("scan_report", "stocks")
        if "all" in lower or "both" in lower:
            return AskIntent("scan_report", "all")
        return AskIntent("scan_report", "stocks")

    if has_watchlist_words and not has_briefing_words:
        match = _WATCHLIST_RE.search(raw)
        name = match.group(1) if match else "core"
        asset = "all"
        if has_crypto_words and not has_stock_words:
            asset = "crypto"
        elif has_stock_words and not has_crypto_words:
            asset = "stocks"
        return AskIntent("watchlist_report", name, asset)

    if has_crypto_words:
        symbol = _pick_crypto_candidate(raw)
        if symbol:
            return AskIntent("crypto_report", symbol)
        return AskIntent("search_fallback")

    if has_stock_words:
        ticker = _pick_stock_candidate(raw)
        if ticker:
            return AskIntent("stock_report", ticker)
        return AskIntent("search_fallback")

    if pair:
        return AskIntent("crypto_compare", pair.group(1).upper(), pair.group(2).upper())

    crypto_symbol = _pick_crypto_candidate(raw)
    if crypto_symbol and _is_common_crypto_symbol(crypto_symbol):
        return AskIntent("crypto_report", crypto_symbol)

    ticker = _pick_stock_candidate(raw)
    if ticker:
        return AskIntent("stock_report", ticker)

    symbol = _pick_crypto_candidate(raw)
    if symbol:
        return AskIntent("crypto_report", symbol)

    return AskIntent("search_fallback")


def extract_terms(text: str) -> list[str]:
    """Extract normalized, de-duplicated content terms from free text."""
    return _extract_tokens(text)
