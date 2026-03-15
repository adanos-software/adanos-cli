"""Local watchlist storage and helpers."""

from __future__ import annotations

import json
from typing import Any

from . import config as cli_config
from .utils import csv_to_list

ASSETS = {"stocks", "crypto"}


def _watchlist_path():
    return cli_config.CONFIG_DIR / "watchlists.json"


def _normalize_store(raw: Any) -> dict[str, dict[str, list[str]]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for name, payload in raw.items():
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(payload, dict):
            continue
        stocks = [s for s in csv_to_list(",".join(map(str, payload.get("stocks") or []))) if s]
        crypto = [s for s in csv_to_list(",".join(map(str, payload.get("crypto") or []))) if s]
        out[name.strip()] = {
            "stocks": stocks,
            "crypto": crypto,
        }
    return out


def load_watchlists() -> dict[str, dict[str, list[str]]]:
    path = _watchlist_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return _normalize_store(raw)


def save_watchlists(data: dict[str, dict[str, list[str]]]) -> None:
    normalized = _normalize_store(data)
    cli_config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _watchlist_path()
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def list_watchlists() -> dict[str, dict[str, list[str]]]:
    return load_watchlists()


def get_watchlist(name: str) -> dict[str, list[str]] | None:
    data = load_watchlists()
    return data.get(name)


def upsert_watchlist_symbols(name: str, asset: str, symbols_csv: str) -> dict[str, list[str]]:
    if asset not in ASSETS:
        raise ValueError(f"Unknown asset '{asset}'")
    symbols = csv_to_list(symbols_csv)
    if not symbols:
        raise ValueError("No symbols provided")

    data = load_watchlists()
    watchlist = data.setdefault(name, {"stocks": [], "crypto": []})
    existing = set(watchlist.get(asset, []))
    merged = list(watchlist.get(asset, []))
    for symbol in symbols:
        if symbol not in existing:
            merged.append(symbol)
            existing.add(symbol)
    watchlist[asset] = merged
    data[name] = watchlist
    save_watchlists(data)
    return watchlist


def remove_watchlist_symbols(name: str, asset: str, symbols_csv: str) -> dict[str, list[str]]:
    if asset not in ASSETS:
        raise ValueError(f"Unknown asset '{asset}'")
    symbols = set(csv_to_list(symbols_csv))
    data = load_watchlists()
    watchlist = data.get(name)
    if watchlist is None:
        raise ValueError(f"Watchlist '{name}' not found")
    current = [symbol for symbol in watchlist.get(asset, []) if symbol not in symbols]
    watchlist[asset] = current
    data[name] = watchlist
    save_watchlists(data)
    return watchlist


def delete_watchlist(name: str) -> bool:
    data = load_watchlists()
    if name not in data:
        return False
    del data[name]
    save_watchlists(data)
    return True
