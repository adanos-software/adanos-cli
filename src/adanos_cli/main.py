"""Adanos CLI entrypoint."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import sys
import time
from argparse import Namespace
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from . import config as cli_config
from .activity_log import activity_log_path, append_activity, read_activity
from .commands.auth import handle_auth_command
from .commands.config import handle_config_command
from .commands.extensions import completion_script, list_plugin_files, plugins_dir
from .config import (
    DEFAULT_BASE_URL,
    load_credentials_file,
    masked_key,
    resolve_runtime_config,
    save_config_file,
)
from .endpoints import ENDPOINTS, invoke_endpoint, is_health_endpoint, list_endpoints
from .nlp import extract_terms, parse_ask_intent
from .shell_history import append_history, load_history, most_recent_command
from .summaries import (
    build_stock_compare_report,
    build_stock_scan_report,
    build_crypto_scan_report,
    build_market_briefing_report,
    build_trending_report,
    build_crypto_compare_report,
    build_crypto_report,
    build_search_fallback_report,
    build_stock_report,
    format_stock_scan_report,
    format_crypto_scan_report,
    format_market_briefing_report,
    format_stock_compare_report,
    format_trending_report,
    format_crypto_compare_report,
    format_crypto_report,
    format_search_fallback_report,
    format_stock_report,
)
from .tty import is_interactive, should_output_json, supports_color
from .update_notifier import format_update_notice, get_update_payload
from .utils import CliUsageError, csv_to_list, print_err, print_json, to_plain, with_json_metadata
from .watchlists import (
    delete_watchlist,
    get_watchlist,
    list_watchlists,
    remove_watchlist_symbols,
    upsert_watchlist_symbols,
)

SUPPORT_CONTACT_EMAIL = "support@adanos.org"
PAID_ACCOUNT_TYPES = {"hobby", "professional"}
DEFAULT_RECOVERY_REQUEST_URL = "https://adanos.org/api/recover"


def _load_sdk_client_class() -> Any:
    try:
        from adanos import AdanosClient

        return AdanosClient
    except ImportError:
        try:
            from stocksentiment import StockSentimentClient

            return StockSentimentClient
        except ImportError as exc:
            raise CliUsageError(
                "Python SDK dependency missing. Install with `pipx install adanos-cli` "
                "or `python3 -m pip install adanos`."
            ) from exc
    except Exception as exc:
        raise CliUsageError(
            "Python SDK dependency missing. Install with `pipx install adanos-cli` "
            "or `python3 -m pip install adanos`."
        ) from exc


def _print_onboarding_guide(base_url: str, *, has_api_key: bool = False) -> None:
    if has_api_key:
        print("API key is already configured.")
        print("Use onboarding only if you want to replace your key.")
    else:
        print("API key is not configured.")

    print("Guided setup (no curl):")
    print("1) If you already have an API key:")
    print("   adanos login --api-key sk_live_xxx")
    print("2) Recommended if you need a new key: run the interactive wizard")
    print("   adanos onboard wizard")
    print("3) Manual alternative:")
    print('   adanos onboard register --name "Your Name" --email "you@example.com" --purpose "CLI usage for stocks and crypto"')
    print("   # wait for the email, then redeem the one-time token")
    print("   adanos onboard redeem --token <delivery_token> --save")
    print("4) If you lost access to an existing key:")
    print('   adanos onboard recover --email "you@example.com"')
    print("5) Start using the API:")
    print('   adanos ask "How does TSLA look?"')
    print(f"API base URL: {base_url}")


def _supports_color() -> bool:
    return supports_color()


def _style(text: str, *, fg: str | None = None, bold: bool = False, dim: bool = False) -> str:
    if not _supports_color():
        return text
    colors = {
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "magenta": "35",
        "cyan": "36",
        "white": "37",
        "orange": "38;5;209",
    }
    codes: list[str] = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if fg and fg in colors:
        codes.append(colors[fg])
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def _print_welcome_screen(base_url: str, *, has_api_key: bool) -> None:
    print(_style("ADANOS CLI", fg="cyan", bold=True))
    print(_style("Stocks + Crypto sentiment for api.adanos.org", dim=True))
    print("")
    key_label = _style("configured", fg="green", bold=True) if has_api_key else _style("not configured", fg="red", bold=True)
    print(f"API base URL: {_style(base_url, fg='blue')}")
    print(f"API key: {key_label}")
    print("")
    print(_style("Examples:", fg="yellow", bold=True))
    print('  adanos ask "How does stock TSLA look?"')
    print('  adanos ask "How many users mention Microsoft?"')
    print('  adanos ask "crypto btc/eth"')
    print("")
    if has_api_key:
        print(_style("Quick start:", fg="green", bold=True))
        print('  adanos ask "stock AAPL"')
        print("  adanos scan --asset stocks --style daytrader")
        print("  adanos endpoint list")
    else:
        print(_style("Setup in 2 steps:", fg="yellow", bold=True))
        print("  1) adanos onboard wizard")
        print("  2) or manual: adanos onboard register ... then redeem the emailed token")
    print("")
    print(_style("Core commands:", fg="cyan", bold=True))
    print("  adanos stock <TICKER>")
    print("  adanos crypto <SYMBOL|SYMBOL/SYMBOL>")
    print("  adanos account")
    print("  adanos briefing --profile investor --from 2026-05-01 --to 2026-05-07")
    print("  adanos watchlist report core --asset all")
    print("")
    print(f"More help: {_style('adanos --help', fg='magenta', bold=True)}")


def _print_start_screen(base_url: str, *, has_api_key: bool, api_key: str | None = None) -> None:
    account_status = _resolve_shell_account_status(base_url, api_key or "") if has_api_key and api_key else None
    api_key_status = _format_shell_api_key_status(has_api_key=has_api_key, account_status=account_status)
    _print_shell_header(base_url, has_api_key=has_api_key, api_key_status=api_key_status)
    print(_style("Start Here", fg="cyan", bold=True))
    if has_api_key:
        print("  1) Verify config: adanos whoami")
        print("  2) Run diagnostics: adanos doctor")
        print("  3) First signal: adanos consensus TSLA")
    else:
        print("  1) Login: adanos login --api-key sk_live_xxx")
        print("  2) Inspect config: adanos whoami")
        print("  3) Run diagnostics: adanos doctor")
    print("")
    print(_style("AI / Automation", fg="cyan", bold=True))
    print("  adanos --quiet capabilities")
    print("  adanos --quiet consensus TSLA")
    print("")
    print(_style("Interactive Shell", fg="cyan", bold=True))
    print("  adanos shell")
    print(_style("Run `adanos --help` for the full command surface.", dim=True))


def _print_update_notice_if_available() -> None:
    if os.getenv("ADANOS_CLI_DISABLE_UPDATE_CHECK"):
        return
    payload = get_update_payload(__version__)
    if payload is None:
        return
    print("")
    print(_style(format_update_notice(payload), fg="yellow", bold=True))


def _print_shell_header(base_url: str, *, has_api_key: bool, api_key_status: str | None = None) -> None:
    logo_lines = [
        "      /\\      ",
        "     /  \\     ",
        "    / /\\ \\    ",
        "   / ____ \\   ",
        "  /_/    \\_\\  ",
    ]
    key_status = api_key_status if api_key_status is not None else (
        _style("configured", fg="green", bold=True) if has_api_key else _style("not configured", fg="red", bold=True)
    )
    details = [
        f"{_style('Adanos Market Sentiment CLI', fg='cyan', bold=True)} {_style(f'v{__version__}', fg='magenta', bold=True)}",
        f"cwd: {_style(str(Path.cwd()), fg='white')}",
        f"api: {_style(base_url, fg='blue')}",
        f"api_key: {key_status}",
    ]

    logo_width = max(len(line) for line in logo_lines)
    row_count = max(len(logo_lines), len(details))
    for idx in range(row_count):
        left_raw = logo_lines[idx] if idx < len(logo_lines) else " " * logo_width
        left = _style(left_raw, fg="orange", bold=True)
        right = details[idx] if idx < len(details) else ""
        print(f"{left}  {right}")

    print(_style("-" * 68, dim=True))


def _print_shell_quickstart(*, has_api_key: bool) -> None:
    print(_style("Quick Start", fg="cyan", bold=True))
    if has_api_key:
        print('  Ask in plain text: "How does TSLA look this week?"')
        print("  Stock report: /stock TSLA")
        print("  Crypto report: /crypto BTC/ETH")
        print("  Screener: /scan --asset stocks --style starter")
        print("  Plan/Credits: /account")
    else:
        print("  1) Configure API key: /onboard wizard")
        print("  2) Or set existing key: /config set --api-key sk_live_xxx")
        print('  3) First query: /ask "How does TSLA look?"')
    print(_style("Type /help for full command catalog.", dim=True))
    print("")


def _print_shell_help(*, has_api_key: bool) -> None:
    print(_style("Guided Help", fg="cyan", bold=True))
    print("  The shell accepts both slash commands and plain text questions.")
    print("")
    print(_style("First Steps", fg="cyan", bold=True))
    if has_api_key:
        print("  1) Ask directly in plain text:")
        print('     How does TSLA look this week?')
        print("  2) Run a sentiment screen:")
        print("     /scan --asset stocks --style daytrader")
        print("  3) Check key plan and monthly credits:")
        print("     /account")
    else:
        print("  1) Configure your API key:")
        print("     /onboard wizard")
        print("  2) Alternative if key already exists:")
        print("     /config set --api-key sk_live_xxx")
        print("  3) Run your first query:")
        print('     /ask "How does TSLA look?"')
    print("")
    print(_style("Command Catalog", fg="cyan", bold=True))
    print("  Setup + Config")
    print("    /onboard guide|wizard|register|redeem")
    print("    /login --api-key sk_live_xxx")
    print("    /logout")
    print("    /auth login|logout|list|switch|current")
    print("    /config show|set|clear")
    print("    /account")
    print("    /whoami")
    print("    /doctor")
    print("    /logs tail|path")
    print("    /completion bash|zsh|fish")
    print("    /plugins dir|list")
    print("")
    print("  Analysis")
    print('    /ask "free text question"')
    print("    /stock TICKER")
    print("    /consensus TICKER")
    print("    /explain TICKER --profile investor")
    print("    /crypto SYMBOL or /crypto BTC/ETH")
    print("    /watch core --kind watchlist --refresh 60")
    print("    /export TSLA --kind consensus --format md")
    print("    /scan --asset stocks|crypto --style starter|daytrader|swing|investor")
    print("    /briefing --profile starter|daytrader|swing|investor|crypto|research|portfolio")
    print("")
    print("  Lists + Platform Queries")
    print("    /watchlist list|show|add|remove|report|delete")
    print("    /trending --platform ... --dimension ...")
    print("    /search --platform ... QUERY")
    print("    /compare --platform ... ASSETS_CSV")
    print("    /stats --platform ...")
    print("    /health --platform all|news-stocks|reddit-stocks|reddit-crypto|x-stocks|polymarket-stocks")
    print("")
    print("  Power / API Coverage")
    print("    /endpoint list")
    print("    /endpoint call <endpoint-id> [params]")
    print("    /capabilities --output json")
    print("    Tip: run /endpoint list to see every supported endpoint id.")
    print("")
    print(_style("Shell Controls", fg="cyan", bold=True))
    print("  /help           show this guide")
    print("  /history        show recent commands")
    print("  /retry          rerun the most recent command")
    print("  /clear          clear screen and redraw header")
    print("  /exit           exit shell")
    print("  /<command> ...  run any CLI command")


def _shell_enter_fullscreen() -> None:
    # Use alternate screen buffer to provide a clean fullscreen-like shell UI.
    if sys.stdin.isatty() and sys.stdout.isatty():
        print("\033[?1049h\033[2J\033[H", end="", flush=True)


def _shell_exit_fullscreen() -> None:
    if sys.stdin.isatty() and sys.stdout.isatty():
        print("\033[?1049l", end="", flush=True)


def _shell_clear_start_screen() -> None:
    # Clear current screen and scrollback so CLI starts with a clean terminal.
    if sys.stdin.isatty() and sys.stdout.isatty():
        print("\033[3J\033[2J\033[H", end="", flush=True)


def _shell_fullscreen_default() -> bool:
    value = str(os.getenv("ADANOS_CLI_FULLSCREEN", "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _resolve_shell_fullscreen(flag_value: bool | None) -> bool:
    if flag_value is not None:
        return bool(flag_value)
    return _shell_fullscreen_default()


def _is_shell_meta_command(token: str) -> bool:
    return token in {"help", "history", "retry", "exit", "quit", "clear"}


def _is_cli_command(token: str) -> bool:
    return token in {
        "onboard",
        "login",
        "logout",
        "auth",
        "config",
        "doctor",
        "whoami",
        "logs",
        "capabilities",
        "completion",
        "plugins",
        "shell",
        "watch",
        "scan",
        "briefing",
        "watchlist",
        "endpoint",
        "stock",
        "crypto",
        "ask",
        "consensus",
        "explain",
        "export",
        "trending",
        "search",
        "compare",
        "stats",
        "health",
        "account",
    }


def _shell_line_to_argv(raw: str) -> list[str] | None:
    line = raw.strip()
    if not line:
        return None

    for prefix in ("adanos-cli ", "adanos "):
        if line.startswith(prefix):
            line = line[len(prefix) :].strip()
            if not line:
                return None
            return shlex.split(line)

    if line.startswith("/"):
        line = line[1:].strip()
        if not line:
            return None
        return shlex.split(line)

    tokens = shlex.split(line)
    if not tokens:
        return None
    head = tokens[0].lower()
    if _is_cli_command(head) or _is_shell_meta_command(head) or head.startswith("--"):
        return tokens

    # Default behavior: treat free text as ask intent.
    return ["ask", raw]


def _normalize_shell_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv

    command = argv[0].lower()
    if command != "scan":
        return argv

    # If --asset is already provided, keep command unchanged.
    if any(token == "--asset" for token in argv[1:]):
        return argv

    # Shorthand: `/scan crypto` or `/scan stocks`
    if len(argv) >= 2 and not argv[1].startswith("--"):
        asset_token = argv[1].lower()
        if asset_token in {"stock", "stocks"}:
            return ["scan", "--asset", "stocks", *argv[2:]]
        if asset_token in {"crypto", "coin", "coins"}:
            return ["scan", "--asset", "crypto", *argv[2:]]

    # Sensible default for `/scan` and `/scan --style ...`
    if len(argv) == 1:
        return ["scan", "--asset", "stocks", "--style", "starter"]
    return ["scan", "--asset", "stocks", *argv[1:]]


def _run_shell(base_url: str, *, has_api_key: bool, use_fullscreen: bool, api_key: str | None = None) -> int:
    account_status = _resolve_shell_account_status(base_url, api_key or "") if has_api_key and api_key else None
    api_key_status = _format_shell_api_key_status(has_api_key=has_api_key, account_status=account_status)
    if use_fullscreen:
        _shell_enter_fullscreen()
    else:
        _shell_clear_start_screen()
    try:
        _print_shell_header(base_url, has_api_key=has_api_key, api_key_status=api_key_status)
        _print_shell_quickstart(has_api_key=has_api_key)
        _print_update_notice_if_available()

        while True:
            try:
                raw = input("adanos-cli> ").strip()
            except EOFError:
                print("\nExiting ADANOS CLI.")
                return 0
            except KeyboardInterrupt:
                print("\nInterrupted. Type /exit to quit.")
                continue

            argv = _shell_line_to_argv(raw)
            if not argv:
                continue
            argv = _normalize_shell_argv(argv)
            history_entry = raw

            command = argv[0].lower()
            if command in {"exit", "quit"}:
                print("Bye.")
                return 0
            if command == "help":
                _print_shell_help(has_api_key=has_api_key)
                continue
            if command == "history":
                entries = load_history(limit=10)
                if not entries:
                    print("No shell history yet.")
                else:
                    print("Recent commands")
                    for idx, entry in enumerate(entries, start=1):
                        print(f"{idx:>2}. {entry}")
                continue
            if command == "retry":
                previous = most_recent_command()
                if not previous:
                    print("No previous command to retry.")
                    continue
                print(f"Retrying: {previous}")
                history_entry = previous
                argv = _normalize_shell_argv(_shell_line_to_argv(previous) or [])
                if not argv:
                    print("Unable to reconstruct previous command.")
                    continue
                command = argv[0].lower()
            if command == "clear":
                print("\033[2J\033[H", end="")
                _print_shell_header(base_url, has_api_key=has_api_key, api_key_status=api_key_status)
                continue
            if command == "shell":
                print_err("usage_error: already running inside shell")
                continue

            append_history(history_entry)
            rc = main(argv, invocation_source="shell")
            if rc != 0:
                print_err(f"command_failed: exit code {rc} | retry with /retry")
    finally:
        if use_fullscreen:
            _shell_exit_fullscreen()


def _normalize_global_cli_flags(argv: list[str]) -> list[str]:
    """Allow global flags to appear after subcommands by hoisting them to the front."""
    value_flags = {"--api-key", "--base-url", "--output"}
    bare_flags = {"--version", "--quiet"}
    command_prefix: list[str] = []
    scan_idx = 0
    while scan_idx < len(argv):
        token = argv[scan_idx]
        if token in bare_flags:
            scan_idx += 1
            continue
        if token in value_flags:
            scan_idx += 2 if scan_idx + 1 < len(argv) else 1
            continue
        if any(token.startswith(prefix + "=") for prefix in value_flags):
            scan_idx += 1
            continue
        if token.startswith("-"):
            break
        command_prefix.append(token.lower())
        scan_idx += 1

    local_only_value_flags: set[str] = set()
    if command_prefix[:2] == ["config", "set"]:
        local_only_value_flags = {"--api-key", "--base-url"}
    if command_prefix[:2] == ["auth", "login"]:
        local_only_value_flags = {"--api-key", "--base-url"}
    if command_prefix[:1] == ["login"]:
        local_only_value_flags = {"--api-key", "--base-url"}

    moved: list[str] = []
    rest: list[str] = []
    idx = 0
    while idx < len(argv):
        token = argv[idx]
        if token in bare_flags:
            moved.append(token)
            idx += 1
            continue
        if token in value_flags:
            if token in local_only_value_flags:
                rest.append(token)
                if idx + 1 < len(argv):
                    rest.append(argv[idx + 1])
                    idx += 2
                    continue
                idx += 1
                continue
            if idx + 1 < len(argv):
                moved.extend([token, argv[idx + 1]])
                idx += 2
                continue
            # Keep invalid trailing flag in place so argparse can raise a proper error.
            rest.append(token)
            idx += 1
            continue
        if any(token.startswith(prefix + "=") for prefix in local_only_value_flags):
            rest.append(token)
            idx += 1
            continue
        if any(token.startswith(prefix + "=") for prefix in value_flags):
            moved.append(token)
            idx += 1
            continue

        rest.append(token)
        idx += 1

    return moved + rest


def _completion_script(shell: str) -> str:
    return completion_script(shell)


def _plugins_dir() -> Path:
    return plugins_dir()


def _list_plugin_files() -> list[dict[str, str]]:
    return list_plugin_files()


def _emit_error(
    *,
    json_mode: bool,
    code: str,
    message: str,
    hint: str | None = None,
    status_code: int | None = None,
) -> None:
    if json_mode:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if hint:
            payload["error"]["hint"] = hint
        if status_code is not None:
            payload["error"]["status_code"] = status_code
        print_json(payload, file=sys.stderr)
        return

    line = f"{code}: {message}"
    if hint:
        line += f" | hint: {hint}"
    print_err(line)


def _capabilities_payload(base_url: str, *, has_api_key: bool) -> dict[str, Any]:
    commands = [
        "onboard",
        "login",
        "logout",
        "auth",
        "config",
        "doctor",
        "whoami",
        "logs",
        "capabilities",
        "completion",
        "plugins",
        "shell",
        "watch",
        "scan",
        "briefing",
        "watchlist",
        "endpoint",
        "stock",
        "crypto",
        "ask",
        "consensus",
        "explain",
        "export",
        "trending",
        "search",
        "compare",
        "stats",
        "health",
        "account",
    ]
    return {
        "kind": "capabilities",
        "command": "capabilities",
        "name": "adanos-cli",
        "version": __version__,
        "api_base_url": base_url,
        "api_key_configured": has_api_key,
        "output_modes": ["text", "json"],
        "error_channel": "stderr",
        "exit_codes": {
            "0": "success",
            "1": "runtime_error",
            "2": "usage_or_auth_error",
        },
        "commands": commands,
        "endpoint_count": len(ENDPOINTS),
        "auth": {
            "header": "X-API-Key",
            "setup": [
                "adanos onboard wizard",
                "adanos onboard register --name ... --email ... --purpose ...",
                "check email for the one-time token",
                "adanos onboard redeem --token <delivery_token> --save",
            ],
            "alternatives": [
                "adanos login --api-key sk_live_xxx",
                "adanos auth login --api-key sk_live_xxx --profile prod",
                "adanos config set --api-key sk_live_xxx",
                "ADANOS_API_KEY env var",
                "--api-key flag",
            ],
        },
        "discovery_commands": [
            "adanos --output json capabilities",
            "adanos --output json endpoint list",
            "adanos --help",
        ],
    }


def _endpoint_parts(endpoint_id: str) -> tuple[str, str]:
    head, _, tail = endpoint_id.partition(".")
    return head, tail or endpoint_id


def _payload_result_count(payload: Any) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return None
    for key in ("results", "stocks", "tokens", "rows", "entries", "sources", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _endpoint_result_payload(endpoint_id: str, data: Any, *, command: str, subcommand: str | None = None) -> dict[str, Any]:
    plain_data = to_plain(data)
    platform, route = _endpoint_parts(endpoint_id)
    payload = with_json_metadata(
        {
            "endpoint": endpoint_id,
            "path": ENDPOINTS[endpoint_id].path,
            "data": plain_data,
        },
        kind="endpoint_result",
        command=command,
        subcommand=subcommand,
        platform=platform,
        route=route,
    )
    result_count = _payload_result_count(plain_data)
    if result_count is not None:
        payload["result_count"] = result_count
    return payload


def _print_capabilities_text(payload: dict[str, Any]) -> None:
    print("CLI capabilities")
    print(f"- name: {payload['name']}")
    print(f"- version: {payload['version']}")
    print(f"- endpoint_count: {payload['endpoint_count']}")
    print(f"- output_modes: {', '.join(payload['output_modes'])}")
    print(f"- error_channel: {payload['error_channel']}")
    print(f"- api_key_configured: {payload['api_key_configured']}")
    print("- discovery:")
    for cmd in payload["discovery_commands"]:
        print(f"  {cmd}")


def _format_logs_entry(entry: dict[str, Any]) -> str:
    argv = [str(token) for token in entry.get("argv", []) if isinstance(token, str)]
    rendered = " ".join(shlex.quote(token) for token in argv)
    return (
        f"[{entry.get('captured_at', 'unknown')}] "
        f"{entry.get('source', 'direct')} rc={entry.get('exit_code', 'n/a')} "
        f"{entry.get('duration_ms', 'n/a')}ms {rendered}"
    )


def _extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            error = detail.get("error")
            if isinstance(error, str) and error.strip():
                return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()

    text = (response.text or "").strip()
    return text if text else f"HTTP {response.status_code}"


def _decode_json_dict(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_account_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == "premium":
        return "professional"
    return raw if raw else "unknown"


def _extract_error_detail(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    detail = data.get("detail")
    return detail if isinstance(detail, dict) else None


def _extract_status_code_from_exception(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    if response is not None and isinstance(getattr(response, "status_code", None), int):
        return int(response.status_code)

    match = re.search(r"Unexpected status code:\s*(\d{3})", str(exc))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_runtime_error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, httpx.Response):
        return _extract_error_message(response)

    content = getattr(exc, "content", None)
    if isinstance(content, (bytes, bytearray)):
        decoded = content.decode(errors="ignore").strip()
        if decoded:
            try:
                payload = json.loads(decoded)
                if isinstance(payload, dict):
                    detail = payload.get("detail")
                    if isinstance(detail, str) and detail.strip():
                        return detail.strip()
                    if isinstance(detail, dict):
                        detail_message = detail.get("message") or detail.get("error")
                        if isinstance(detail_message, str) and detail_message.strip():
                            return detail_message.strip()
            except Exception:
                pass
            return decoded.replace("\n", " ")

    text = str(exc).strip().replace("\n", " ")
    return text if text else "Unexpected runtime error"


def _classify_runtime_error(exc: Exception) -> tuple[str, str, str | None, int | None]:
    status_code = _extract_status_code_from_exception(exc)
    message = _extract_runtime_error_message(exc)
    lowered = message.lower()

    if status_code == 401:
        return (
            "auth_failed",
            "Invalid or revoked API key.",
            "Update your key with `adanos config set --api-key sk_live_xxx`.",
            401,
        )

    if status_code == 429:
        is_monthly_quota = any(
            token in lowered
            for token in (
                "monthly api limit exceeded",
                "free tier limit",
                "requests per month",
                "1st of next month",
                "out of api credits",
            )
        )
        if is_monthly_quota:
            return (
                "out_of_api_credits",
                "Out of API credits for the current monthly quota.",
                (
                    "Run `adanos account` for quota status. "
                    f"Upgrade options are hobby/professional via {SUPPORT_CONTACT_EMAIL}."
                ),
                429,
            )
        return (
            "rate_limited",
            "Rate limit exceeded. Retry shortly.",
            "If this persists, run `adanos account` to inspect your plan and quota.",
            429,
        )

    return ("runtime_error", message, None, status_code)


def _request_onboard_register(base_url: str, payload: dict[str, str]) -> tuple[int, dict[str, Any] | None, str]:
    with httpx.Client(base_url=base_url, timeout=30.0) as http:
        response = http.post("/auth/v1/register", json=payload)
    data = _decode_json_dict(response)
    message = _extract_error_message(response)
    return response.status_code, data, message


def _request_onboard_redeem(base_url: str, token: str) -> tuple[int, dict[str, Any] | None, str]:
    with httpx.Client(base_url=base_url, timeout=30.0) as http:
        response = http.post("/auth/v1/key/redeem", json={"token": token})
    data = _decode_json_dict(response)
    message = _extract_error_message(response)
    return response.status_code, data, message


def _request_onboard_recover(recovery_url: str, payload: dict[str, str]) -> tuple[int, dict[str, Any] | None, str]:
    with httpx.Client(timeout=30.0) as http:
        response = http.post(recovery_url, json=payload)
    data = _decode_json_dict(response)
    message = _extract_error_message(response)
    return response.status_code, data, message


def _request_account_status(
    base_url: str, api_key: str, *, timeout_s: float = 30.0
) -> tuple[int, dict[str, Any] | None, str, dict[str, str]]:
    headers = {"X-API-Key": api_key}
    with httpx.Client(base_url=base_url, timeout=timeout_s) as http:
        response = http.get("/reddit/stocks/v1/stats", headers=headers)
    data = _decode_json_dict(response)
    message = _extract_error_message(response)
    header_map = {str(key).lower(): value for key, value in response.headers.items()}
    return response.status_code, data, message, header_map


def _header_get(headers: dict[str, str], name: str) -> str | None:
    return headers.get(name.lower())


def _build_account_status_payload(
    *,
    base_url: str,
    status_code: int,
    headers: dict[str, str],
    data: dict[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    detail = _extract_error_detail(data)

    account_type = _coerce_account_type(
        _header_get(headers, "X-Account-Type")
        or (detail or {}).get("account_type")
        or (data or {}).get("plan")
    )

    limit_raw = _header_get(headers, "X-RateLimit-Limit-Monthly") or _header_get(headers, "X-RateLimit-Limit")
    remaining_raw = _header_get(headers, "X-RateLimit-Remaining-Monthly") or _header_get(headers, "X-RateLimit-Remaining")
    used_raw = _header_get(headers, "X-RateLimit-Used-Monthly")

    limit = None if str(limit_raw or "").strip().lower() == "unlimited" else _to_optional_int(limit_raw)
    remaining = None if str(remaining_raw or "").strip().lower() == "unlimited" else _to_optional_int(remaining_raw)
    used = _to_optional_int(used_raw)

    if isinstance(detail, dict):
        if limit is None:
            limit = _to_optional_int(detail.get("limit"))
        if used is None:
            used = _to_optional_int(detail.get("used"))
        if account_type == "unknown":
            account_type = _coerce_account_type(detail.get("account_type"))

    if used is None and limit is not None and remaining is not None:
        used = max(0, limit - remaining)
    if remaining is None and limit is not None and used is not None:
        remaining = max(0, limit - used)

    lowered_message = (message or "").lower()
    out_of_credits = status_code == 429 and (
        "monthly api limit exceeded" in lowered_message
        or "free tier limit" in lowered_message
        or "requests per month" in lowered_message
    )

    paid_active = account_type in PAID_ACCOUNT_TYPES
    upgrade_options: list[str]
    if account_type == "free" or out_of_credits:
        upgrade_options = ["hobby", "professional"]
    elif account_type == "hobby":
        upgrade_options = ["professional"]
    else:
        upgrade_options = []

    status_label = "active"
    if out_of_credits:
        status_label = "out_of_credits"
    elif paid_active:
        status_label = "paid_active"

    return {
        "kind": "account_status",
        "command": "account",
        "api_base_url": base_url,
        "status": status_label,
        "status_code": status_code,
        "account_type": account_type,
        "paid_active": paid_active,
        "out_of_credits": out_of_credits,
        "monthly_limit": limit,
        "monthly_used": used,
        "monthly_remaining": remaining,
        "upgrade_options": upgrade_options,
        "upgrade_contact": SUPPORT_CONTACT_EMAIL if upgrade_options else None,
        "message": message,
    }


def _print_account_status(payload: dict[str, Any]) -> None:
    print("Account status")
    print(f"- API: {payload.get('api_base_url')}")
    print(f"- Plan: {payload.get('account_type', 'unknown')}")

    if payload.get("paid_active"):
        print("- Status: paid plan active")
    elif payload.get("out_of_credits"):
        print("- Status: out of API credits")
    else:
        print("- Status: active")

    monthly_limit = payload.get("monthly_limit")
    monthly_used = payload.get("monthly_used")
    monthly_remaining = payload.get("monthly_remaining")
    if monthly_limit is None:
        print("- Monthly credits: unlimited")
        if monthly_used is not None:
            print(f"- Monthly used: {monthly_used}")
    else:
        used_label = monthly_used if monthly_used is not None else "unknown"
        remaining_label = monthly_remaining if monthly_remaining is not None else "unknown"
        print(f"- Monthly credits: {used_label}/{monthly_limit} used ({remaining_label} remaining)")

    upgrade_options = payload.get("upgrade_options") or []
    if upgrade_options:
        options = ", ".join(str(option) for option in upgrade_options)
        print(f"- Upgrade options: {options} ({SUPPORT_CONTACT_EMAIL})")

    note = str(payload.get("message") or "").strip()
    if note:
        print(f"- Note: {note}")


def _build_whoami_payload(
    runtime_cfg: cli_config.RuntimeConfig,
    *,
    account_payload: dict[str, Any] | None,
    account_error: dict[str, Any] | None,
) -> dict[str, Any]:
    status = "missing_api_key"
    if runtime_cfg.api_key:
        status = "configured"
    if account_payload is not None:
        status = str(account_payload.get("status") or status)
    elif isinstance(account_error, dict) and account_error.get("code") == "auth_failed":
        status = "auth_failed"

    payload: dict[str, Any] = {
        "kind": "whoami",
        "command": "whoami",
        "version": __version__,
        "status": status,
        "api_base_url": runtime_cfg.base_url,
        "base_url_source": runtime_cfg.base_url_source,
        "profile": runtime_cfg.profile_name,
        "api_key_configured": bool(runtime_cfg.api_key),
        "api_key_masked": masked_key(runtime_cfg.api_key),
        "api_key_source": runtime_cfg.api_key_source,
        "config_path": str(cli_config.CONFIG_PATH),
        "credentials_path": str(cli_config.CREDENTIALS_PATH),
    }

    if account_payload is not None:
        payload.update(
            {
                "account_type": account_payload.get("account_type"),
                "paid_active": account_payload.get("paid_active"),
                "out_of_credits": account_payload.get("out_of_credits"),
                "monthly_limit": account_payload.get("monthly_limit"),
                "monthly_used": account_payload.get("monthly_used"),
                "monthly_remaining": account_payload.get("monthly_remaining"),
            }
        )

    if account_error is not None:
        payload["account_error"] = account_error

    return payload


def _print_whoami(payload: dict[str, Any]) -> None:
    print("Who am I")
    print(f"- Version: {payload.get('version')}")
    print(f"- API base URL: {payload.get('api_base_url')}")
    print(f"- Base URL source: {payload.get('base_url_source')}")
    if payload.get("profile"):
        print(f"- Profile: {payload.get('profile')}")
    print(f"- API key: {payload.get('api_key_masked')}")
    print(f"- API key source: {payload.get('api_key_source')}")
    print(f"- Status: {payload.get('status')}")
    print(f"- Config path: {payload.get('config_path')}")
    print(f"- Credentials path: {payload.get('credentials_path')}")
    if payload.get("account_type"):
        print(f"- Account type: {payload.get('account_type')}")
    if payload.get("monthly_limit") is not None:
        print(
            f"- Monthly credits: {payload.get('monthly_used')}/{payload.get('monthly_limit')} "
            f"used ({payload.get('monthly_remaining')} remaining)"
        )
    account_error = payload.get("account_error")
    if isinstance(account_error, dict):
        print(f"- Account check: {account_error.get('message', 'unavailable')}")


def _inspect_account_status(
    base_url: str,
    api_key: str,
    *,
    timeout_s: float = 5.0,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not api_key:
        return None, {
            "code": "api_key_missing",
            "message": "API key is not configured.",
        }

    try:
        status_code, data, message, headers = _request_account_status(
            base_url,
            api_key,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        return None, {
            "code": "account_status_unavailable",
            "message": _extract_runtime_error_message(exc),
        }

    if status_code in {200, 429}:
        return (
            _build_account_status_payload(
                base_url=base_url,
                status_code=status_code,
                headers=headers,
                data=data,
                message="" if status_code == 200 else message,
            ),
            None,
        )

    if status_code == 401:
        return None, {
            "code": "auth_failed",
            "message": "Invalid or revoked API key.",
            "status_code": 401,
        }

    return None, {
        "code": "account_status_failed",
        "message": message,
        "status_code": status_code,
    }


def _build_doctor_payload(runtime_cfg: cli_config.RuntimeConfig) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        {
            "name": "CLI Version",
            "status": "pass",
            "message": f"v{__version__}",
        },
        {
            "name": "Config Directory",
            "status": "pass",
            "message": str(cli_config.CONFIG_DIR),
        },
    ]

    credentials_payload = load_credentials_file()
    credentials_profiles = credentials_payload.get("profiles") or {}
    has_local_credentials = any(
        bool(str((entry or {}).get("api_key") or "").strip())
        for entry in credentials_profiles.values()
        if isinstance(entry, dict)
    )
    if runtime_cfg.api_key:
        checks.append(
            {
                "name": "Credentials",
                "status": "pass",
                "message": (
                    f"{masked_key(runtime_cfg.api_key)} (source: {runtime_cfg.api_key_source}"
                    + (f", profile: {runtime_cfg.profile_name}" if runtime_cfg.profile_name else "")
                    + ")"
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "Credentials",
                "status": "fail",
                "message": "No API key configured",
                "detail": "Priority: --api-key > ADANOS_API_KEY > active profile credentials",
                "next_step": "Run: adanos login --api-key sk_live_xxx",
            }
        )

    if cli_config.CREDENTIALS_PATH.exists() and os.name != "nt":
        try:
            mode = cli_config.CREDENTIALS_PATH.stat().st_mode & 0o777
            checks.append(
                {
                    "name": "Credentials File Permissions",
                    "status": "pass" if mode == 0o600 else "warn",
                    "message": f"{oct(mode)} at {cli_config.CREDENTIALS_PATH}",
                    "next_step": "Restrict this file to 0600 if you manage it outside the CLI." if mode != 0o600 else None,
                }
            )
        except OSError as exc:
            checks.append(
                {
                    "name": "Credentials File Permissions",
                    "status": "warn",
                    "message": str(exc),
                    "next_step": "Re-save credentials with `adanos login` to let the CLI recreate the file.",
                }
            )
    elif has_local_credentials:
        checks.append(
            {
                "name": "Credentials File Permissions",
                "status": "warn",
                "message": "Permission check unavailable on this platform",
                "detail": "The CLI could not verify file mode bits here.",
            }
        )

    account_payload, account_error = _inspect_account_status(
        runtime_cfg.base_url,
        runtime_cfg.api_key,
    )
    if account_payload is not None:
        account_type = str(account_payload.get("account_type") or "unknown")
        if account_payload.get("out_of_credits"):
            checks.append(
                {
                    "name": "API Validation",
                    "status": "warn",
                    "message": f"Valid key, but monthly quota exhausted ({account_type})",
                    "next_step": "Run: adanos account",
                }
            )
        else:
            checks.append(
                {
                    "name": "API Validation",
                    "status": "pass",
                    "message": f"Valid key ({account_type})",
                }
            )
    elif isinstance(account_error, dict):
        next_step = None
        detail = None
        if account_error.get("code") == "api_key_missing":
            detail = "Skipped because credentials are not configured."
            next_step = "Run: adanos login --api-key sk_live_xxx"
        elif account_error.get("code") == "auth_failed":
            next_step = "Run: adanos login --api-key <fresh_key>"
        checks.append(
            {
                "name": "API Validation",
                "status": "fail",
                "message": str(account_error.get("message") or "Unavailable"),
                "detail": detail,
                "next_step": next_step,
            }
        )

    ok = not any(check["status"] == "fail" for check in checks)
    return {"kind": "doctor", "command": "doctor", "ok": ok, "checks": checks}


def _doctor_visible_checks(payload: dict[str, Any], *, verbose: bool) -> list[dict[str, Any]]:
    checks = [check for check in payload.get("checks", []) if isinstance(check, dict)]
    if verbose:
        return checks
    return [check for check in checks if str(check.get("status") or "") in {"warn", "fail"}]


def _doctor_pass_summary(payload: dict[str, Any]) -> str:
    checks = [check for check in payload.get("checks", []) if isinstance(check, dict)]
    api_validation = next((check for check in checks if check.get("name") == "API Validation"), None)
    if isinstance(api_validation, dict):
        message = str(api_validation.get("message") or "").strip()
        if message:
            return f"No issues found. {message}"
    return "No issues found."


def _print_doctor(payload: dict[str, Any], *, verbose: bool) -> None:
    print("Doctor")
    visible_checks = _doctor_visible_checks(payload, verbose=verbose)
    if not visible_checks:
        print(f"- [pass] {_doctor_pass_summary(payload)}")
        print("  detail: Use `adanos whoami` for active identity details.")
        print("  next: Run `adanos doctor --verbose` for the full check list.")
        return

    for check in visible_checks:
        print(f"- [{check.get('status', 'unknown')}] {check.get('name', 'Unknown')}: {check.get('message', '')}")
        detail = str(check.get("detail") or "").strip()
        if detail:
            print(f"  detail: {detail}")
        next_step = str(check.get("next_step") or "").strip()
        if next_step:
            print(f"  next: {next_step}")

    if not verbose:
        hidden_passes = sum(
            1
            for check in payload.get("checks", [])
            if isinstance(check, dict) and str(check.get("status") or "") == "pass"
        )
        if hidden_passes:
            print(f"- [info] {hidden_passes} passing checks hidden. Use --verbose for the full list.")


def _run_whoami(runtime_cfg: cli_config.RuntimeConfig, *, json_mode: bool) -> int:
    account_payload, account_error = _inspect_account_status(
        runtime_cfg.base_url,
        runtime_cfg.api_key,
    )
    payload = _build_whoami_payload(
        runtime_cfg,
        account_payload=account_payload,
        account_error=account_error,
    )
    if json_mode:
        print_json(payload)
    else:
        _print_whoami(payload)
    return 0


def _run_doctor(runtime_cfg: cli_config.RuntimeConfig, *, json_mode: bool, verbose: bool) -> int:
    payload = _build_doctor_payload(runtime_cfg)
    if json_mode:
        print_json(payload)
    else:
        _print_doctor(payload, verbose=verbose)
    return 0 if payload.get("ok") else 1


def _run_logs_path(*, json_mode: bool) -> int:
    payload = {
        "ok": True,
        "kind": "logs_path",
        "command": "logs",
        "subcommand": "path",
        "path": str(activity_log_path()),
    }
    if json_mode:
        print_json(payload)
    else:
        print(payload["path"])
    return 0


def _run_logs_tail(args: Namespace, *, json_mode: bool) -> int:
    entries = read_activity(
        limit=max(1, int(args.limit)),
        command=getattr(args, "log_command", None),
        source=getattr(args, "source", None),
    )
    payload = {
        "ok": True,
        "kind": "logs_tail",
        "command": "logs",
        "subcommand": "tail",
        "path": str(activity_log_path()),
        "entries": entries,
    }
    if json_mode:
        print_json(payload)
        return 0

    if not entries:
        print("No CLI activity logs yet.")
        return 0

    for entry in entries:
        print(_format_logs_entry(entry))
    return 0


def _run_account_status(args: Namespace, base_url: str, api_key: str, *, json_mode: bool) -> int:
    status_code, data, message, headers = _request_account_status(base_url, api_key)

    if status_code not in {200, 401, 429}:
        _emit_error(
            json_mode=json_mode,
            code="account_status_failed",
            message=message,
            status_code=status_code,
        )
        return 1

    if status_code == 401:
        _emit_error(
            json_mode=json_mode,
            code="auth_failed",
            message="Invalid or revoked API key.",
            hint="Update your key with `adanos config set --api-key sk_live_xxx`.",
            status_code=401,
        )
        return 2

    payload = _build_account_status_payload(
        base_url=base_url,
        status_code=status_code,
        headers=headers,
        data=data,
        message="" if status_code == 200 else message,
    )
    if json_mode:
        print_json(payload)
    else:
        _print_account_status(payload)
    return 0


def _resolve_shell_account_status(base_url: str, api_key: str) -> dict[str, Any] | None:
    """Best-effort account lookup for shell header context (non-fatal)."""
    try:
        status_code, data, message, headers = _request_account_status(base_url, api_key, timeout_s=2.0)
    except Exception:
        return None

    if status_code not in {200, 429}:
        return None

    return _build_account_status_payload(
        base_url=base_url,
        status_code=status_code,
        headers=headers,
        data=data,
        message=message,
    )


def _format_shell_api_key_status(*, has_api_key: bool, account_status: dict[str, Any] | None) -> str:
    if not has_api_key:
        return _style("not configured", fg="red", bold=True)
    if not account_status:
        return _style("configured", fg="green", bold=True)

    account_type = str(account_status.get("account_type") or "unknown").lower()
    monthly_limit = account_status.get("monthly_limit")
    monthly_remaining = account_status.get("monthly_remaining")

    if account_type == "free":
        if isinstance(monthly_limit, int) and isinstance(monthly_remaining, int):
            label = f"free ({monthly_remaining}/{monthly_limit} left)"
        elif isinstance(monthly_limit, int):
            label = f"free (limit {monthly_limit}/month)"
        else:
            label = "free"

        if account_status.get("out_of_credits"):
            return _style(label, fg="red", bold=True)
        return _style(label, fg="yellow", bold=True)

    if account_type in PAID_ACCOUNT_TYPES:
        return _style(f"{account_type} (paid)", fg="green", bold=True)

    if account_type not in {"unknown", "configured"}:
        return _style(f"configured ({account_type})", fg="green", bold=True)
    return _style("configured", fg="green", bold=True)


def _prompt_non_empty(label: str, *, default: str | None = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("Please provide a value.")


def _prompt_secret_non_empty(label: str) -> str:
    while True:
        value = getpass(f"{label}: ").strip()
        if value:
            return value
        print("Please provide a value.")


def _prompt_yes_no(label: str, *, default_yes: bool = True) -> bool:
    default_hint = "Y/n" if default_yes else "y/N"
    raw = input(f"{label} ({default_hint}): ").strip().lower()
    if not raw:
        return default_yes
    if raw in {"y", "yes"}:
        return True
    if raw in {"n", "no"}:
        return False
    return default_yes


def _run_onboard_register(args: Namespace, base_url: str, *, json_mode: bool) -> int:
    payload: dict[str, str] = {
        "name": args.name,
        "email": args.email,
        "purpose": args.purpose,
    }
    if args.company_name:
        payload["company_name"] = args.company_name

    status_code, data, message = _request_onboard_register(base_url, payload)
    if status_code not in {200, 202}:
        _emit_error(
            json_mode=json_mode,
            code="onboard_register_failed",
            message=message,
            hint="If you already registered, check your email or use `adanos onboard recover --email ...`",
            status_code=status_code,
        )
        return 1

    if not isinstance(data, dict):
        _emit_error(
            json_mode=json_mode,
            code="onboard_register_failed",
            message="Response did not include structured registration data",
            status_code=status_code,
        )
        return 1

    email = str(data.get("email") or args.email)

    if json_mode:
        print_json(
            with_json_metadata(
                data,
                kind="onboard_registration",
                command="onboard",
                subcommand="register",
            )
        )
    else:
        print("Registration accepted.")
        print(f"Email: {email}")
        print(str(data.get("message") or "Check your email for the secure verification link."))
        print("Next command:")
        print("adanos onboard redeem --token <delivery_token> --save")

    return 0


def _run_onboard_redeem(args: Namespace, base_url: str, *, json_mode: bool) -> int:
    token = args.token.strip()
    status_code, data, message = _request_onboard_redeem(base_url, token)
    if status_code != 200:
        _emit_error(
            json_mode=json_mode,
            code="onboard_redeem_failed",
            message=message,
            hint="Ensure token format is kt_... and token is unused",
            status_code=status_code,
        )
        return 1

    if not isinstance(data, dict):
        _emit_error(
            json_mode=json_mode,
            code="onboard_redeem_failed",
            message="Response did not include structured key data",
            status_code=status_code,
        )
        return 1

    api_key = str(data.get("api_key") or "")
    if not api_key:
        _emit_error(
            json_mode=json_mode,
            code="onboard_redeem_failed",
            message="Response did not include an API key",
        )
        return 1

    if args.save:
        save_config_file(api_key=api_key, base_url=base_url)

    if json_mode:
        print_json(
            with_json_metadata(
                data,
                kind="onboard_redeem",
                command="onboard",
                subcommand="redeem",
                saved=bool(args.save),
            )
        )
    else:
        print("API key retrieved.")
        print(f"Plan: {data.get('plan', 'unknown')}")
        print(f"Email: {data.get('email', 'unknown')}")
        print(f"Retrieved at: {data.get('retrieved_at', 'unknown')}")
        print(f"API key: {masked_key(api_key)}")
        if args.save:
            print(f"Credentials saved: {cli_config.CREDENTIALS_PATH}")
            print(f"Config saved: {cli_config.CONFIG_PATH}")
            print('Try now: adanos ask "crypto btc/eth"')
        else:
            print(f"Save now: adanos config set --api-key {api_key}")

    return 0


def _run_onboard_recover(args: Namespace, *, json_mode: bool) -> int:
    recovery_url = str(args.recovery_url or DEFAULT_RECOVERY_REQUEST_URL).strip()
    status_code, data, message = _request_onboard_recover(recovery_url, {"email": args.email})
    if status_code not in {200, 202}:
        _emit_error(
            json_mode=json_mode,
            code="onboard_recover_failed",
            message=message if message else "Recovery request failed",
            hint="Retry later or open https://adanos.org/key to use the hosted recovery form.",
            status_code=status_code,
        )
        return 1

    if not isinstance(data, dict) or data.get("success") is not True:
        _emit_error(
            json_mode=json_mode,
            code="onboard_recover_failed",
            message="Response did not include structured recovery data",
            status_code=status_code,
        )
        return 1

    if json_mode:
        print_json(
            with_json_metadata(
                data,
                kind="onboard_recovery",
                command="onboard",
                subcommand="recover",
            )
        )
    else:
        print("Recovery request accepted.")
        print(str(data.get("message") or "If an account exists, further recovery instructions will be sent separately."))
        print("Next step:")
        print("  Check your email for the secure recovery link.")

    return 0


def _run_onboard_wizard(args: Namespace, base_url: str, *, json_mode: bool, runtime_has_key: bool) -> int:
    if json_mode:
        _emit_error(
            json_mode=True,
            code="onboard_wizard_unsupported",
            message="Interactive wizard is only available in text mode",
            hint="Use `adanos onboard register ...`, then redeem the emailed token with `adanos onboard redeem ... --save`",
        )
        return 2

    if not is_interactive():
        _emit_error(
            json_mode=False,
            code="onboard_wizard_unsupported",
            message="Interactive wizard requires a TTY terminal",
            hint="Use explicit commands: onboard register, then onboard redeem",
        )
        return 2

    print("Adanos onboarding wizard")
    print(f"API base URL: {base_url}")
    if runtime_has_key:
        print("An API key is already configured.")
        if not _prompt_yes_no("Do you want to replace it?", default_yes=False):
            print("Keeping existing key. Setup finished.")
            return 0
    elif _prompt_yes_no("Do you already have an API key?", default_yes=False):
        api_key = _prompt_secret_non_empty("Existing API key")
        save_config_file(api_key=api_key, base_url=base_url)
        print("API key stored.")
        print(f"Credentials saved: {cli_config.CREDENTIALS_PATH}")
        print(f"Config saved: {cli_config.CONFIG_PATH}")
        print('Next: adanos ask "How does TSLA look?"')
        return 0

    name = _prompt_non_empty("Your name")
    email = _prompt_non_empty("Your email")
    purpose = _prompt_non_empty("Usage purpose", default="CLI usage for stocks and crypto")
    company_name = input("Company (optional): ").strip()

    payload: dict[str, str] = {"name": name, "email": email, "purpose": purpose}
    if company_name:
        payload["company_name"] = company_name

    print("")
    print("Registering your account...")
    status_code, data, message = _request_onboard_register(base_url, payload)
    if status_code not in {200, 202} or not isinstance(data, dict):
        _emit_error(
            json_mode=False,
            code="onboard_register_failed",
            message=message if message else "Registration failed",
            hint="You can retry with `adanos onboard register ...`",
            status_code=status_code,
        )
        return 1

    print("Registration accepted.")
    print(str(data.get("message") or "Check your email for the secure verification link."))

    print("")
    if not _prompt_yes_no("Do you already have the delivery token from your email?", default_yes=False):
        print("Next step:")
        print("  Check your email for the secure verification link.")
        print("  adanos onboard redeem --token <delivery_token> --save")
        return 0

    token = _prompt_non_empty("Delivery token")
    print("Redeeming token...")
    redeem_status, redeem_data, redeem_message = _request_onboard_redeem(base_url, token)
    if redeem_status != 200 or not isinstance(redeem_data, dict):
        _emit_error(
            json_mode=False,
            code="onboard_redeem_failed",
            message=redeem_message if redeem_message else "Token redemption failed",
            hint="Retry with `adanos onboard redeem --token <delivery_token> --save`",
            status_code=redeem_status,
        )
        return 1

    api_key = str(redeem_data.get("api_key") or "").strip()
    if not api_key:
        _emit_error(
            json_mode=False,
            code="onboard_redeem_failed",
            message="Response did not include an API key",
        )
        return 1

    save_config_file(api_key=api_key, base_url=base_url)
    print("API key retrieved and stored.")
    print(f"Credentials saved: {cli_config.CREDENTIALS_PATH}")
    print(f"Config saved: {cli_config.CONFIG_PATH}")
    print('Next: adanos ask "How does TSLA look?"')
    return 0


def _add_period_args(parser: argparse.ArgumentParser, *, default_days: int) -> None:
    parser.add_argument("--from", dest="from_", help="Recommended inclusive UTC start date (YYYY-MM-DD)")
    parser.add_argument("--to", help="Recommended inclusive UTC end date (YYYY-MM-DD)")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=f"Legacy lookback shorthand in days (default: {default_days}; prefer --from/--to)",
    )


def _period_from_args(args: Namespace) -> dict[str, Any]:
    return {
        "days": getattr(args, "days", None),
        "from_": getattr(args, "from_", None),
        "to": getattr(args, "to", None),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adanos",
        description=(
            "Comprehensive CLI for api.adanos.org. Supports all OpenAPI endpoints for "
            "News Stocks, Reddit Stocks, Reddit Crypto, X/Twitter Stocks, and Polymarket Stocks."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Start here:\n"
            "  adanos login --api-key sk_live_xxx\n"
            "  adanos whoami\n"
            "  adanos doctor\n"
            "  adanos shell\n"
            "\n"
            "Automation / AI:\n"
            "  adanos --quiet capabilities\n"
            "  adanos --quiet consensus TSLA\n"
            "\n"
            "Auth resolution:\n"
            "  --api-key flag > ADANOS_API_KEY env var > active profile in credentials.json\n"
            "\n"
            "Output:\n"
            "  Human-readable by default. Use --output json / --quiet for machines.\n"
            "  Direct CLI invocations auto-switch to JSON when stdout is piped."
        ),
    )
    parser.add_argument("--api-key", help="Override API key for this call")
    parser.add_argument("--base-url", help=f"Override base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output mode for agent/human consumption")
    parser.add_argument("--quiet", action="store_true", help="Suppress status-style text output; implies JSON")
    parser.add_argument("--version", action="store_true", help="Print CLI version and exit")

    subs = parser.add_subparsers(dest="command")

    p_onboard = subs.add_parser("onboard", help="Guided API key onboarding without curl")
    onboard_subs = p_onboard.add_subparsers(dest="onboard_cmd")

    p_onboard_guide = onboard_subs.add_parser("guide", help="Show guided onboarding steps")
    p_onboard_guide.set_defaults(_handler="onboard_guide")

    p_onboard_wizard = onboard_subs.add_parser("wizard", help="Interactive guided setup with prompts")
    p_onboard_wizard.add_argument("--json", action="store_true")
    p_onboard_wizard.set_defaults(_handler="onboard_wizard")

    p_onboard_register = onboard_subs.add_parser("register", help="Start email verification for a new API key")
    p_onboard_register.add_argument("--name", required=True, help="Your full name")
    p_onboard_register.add_argument("--email", required=True, help="Your email address")
    p_onboard_register.add_argument("--purpose", required=True, help="How you will use the API")
    p_onboard_register.add_argument("--company-name", help="Optional company/organization")
    p_onboard_register.add_argument("--json", action="store_true")
    p_onboard_register.set_defaults(_handler="onboard_register")

    p_onboard_redeem = onboard_subs.add_parser("redeem", help="Redeem the one-time token from your email to get the API key")
    p_onboard_redeem.add_argument("--token", required=True, help="One-time delivery token (kt_...)")
    p_onboard_redeem.add_argument("--save", action="store_true", help="Save API key directly into local config")
    p_onboard_redeem.add_argument("--json", action="store_true")
    p_onboard_redeem.set_defaults(_handler="onboard_redeem")

    p_onboard_recover = onboard_subs.add_parser("recover", help="Request a recovery email for an existing API key")
    p_onboard_recover.add_argument("--email", required=True, help="Registered email address for the API account")
    p_onboard_recover.add_argument("--recovery-url", help=argparse.SUPPRESS)
    p_onboard_recover.add_argument("--json", action="store_true")
    p_onboard_recover.set_defaults(_handler="onboard_recover")

    p_onboard.set_defaults(_handler="onboard_guide")

    p_auth = subs.add_parser("auth", help="Manage local auth profiles and active credentials")
    auth_subs = p_auth.add_subparsers(dest="auth_cmd", required=True)

    p_auth_login = auth_subs.add_parser(
        "login",
        help="Store an API key in a local profile",
        formatter_class=argparse.RawTextHelpFormatter,
        description="Store an API key in a local profile.",
        epilog=(
            "Non-interactive:\n"
            "  --api-key is required when stdin/stdout is not a TTY.\n"
            "\n"
            "Examples:\n"
            "  adanos auth login --api-key sk_live_xxx --profile prod\n"
            "  adanos login --api-key sk_live_xxx\n"
        ),
    )
    p_auth_login.add_argument("--api-key", help="API key to store")
    p_auth_login.add_argument("--profile", help="Profile name to create or update")
    p_auth_login.add_argument("--base-url", help="Optional base URL to store globally")
    p_auth_login.add_argument("--json", action="store_true")
    p_auth_login.set_defaults(_handler="auth_login")

    p_auth_logout = auth_subs.add_parser("logout", help="Remove a stored profile")
    p_auth_logout.add_argument("--profile", help="Profile name to remove (default: active profile)")
    p_auth_logout.add_argument("--json", action="store_true")
    p_auth_logout.set_defaults(_handler="auth_logout")

    p_auth_list = auth_subs.add_parser("list", help="List configured auth profiles")
    p_auth_list.add_argument("--json", action="store_true")
    p_auth_list.set_defaults(_handler="auth_list")

    p_auth_switch = auth_subs.add_parser("switch", help="Switch the active auth profile")
    p_auth_switch.add_argument("profile", help="Profile name to activate")
    p_auth_switch.add_argument("--json", action="store_true")
    p_auth_switch.set_defaults(_handler="auth_switch")

    p_auth_current = auth_subs.add_parser("current", help="Show the active auth profile")
    p_auth_current.add_argument("--json", action="store_true")
    p_auth_current.set_defaults(_handler="auth_current")

    p_login = subs.add_parser(
        "login",
        help="Shortcut for `adanos auth login`",
        formatter_class=argparse.RawTextHelpFormatter,
        description="Shortcut for `adanos auth login`.",
        epilog=(
            "Non-interactive:\n"
            "  --api-key is required when stdin/stdout is not a TTY.\n"
            "\n"
            "Examples:\n"
            "  adanos login --api-key sk_live_xxx\n"
            "  adanos login --api-key sk_live_xxx --profile prod\n"
        ),
    )
    p_login.add_argument("--api-key", help="API key to store")
    p_login.add_argument("--profile", help="Profile name to create or update")
    p_login.add_argument("--base-url", help="Optional base URL to store globally")
    p_login.add_argument("--json", action="store_true")
    p_login.set_defaults(_handler="auth_login")

    p_logout = subs.add_parser("logout", help="Shortcut for `adanos auth logout`")
    p_logout.add_argument("--profile", help="Profile name to remove (default: active profile)")
    p_logout.add_argument("--json", action="store_true")
    p_logout.set_defaults(_handler="auth_logout")

    p_config = subs.add_parser("config", help="Manage local CLI config")
    cfg_subs = p_config.add_subparsers(dest="config_cmd", required=True)
    p_cfg_set = cfg_subs.add_parser("set", help="Set API key and optional base URL")
    p_cfg_set.add_argument("--api-key", required=True)
    p_cfg_set.add_argument("--base-url")
    p_cfg_set.add_argument("--profile", help="Profile name to update instead of the active profile")
    p_cfg_set.add_argument("--json", action="store_true")
    p_cfg_set.set_defaults(_handler="config_set")

    p_cfg_show = cfg_subs.add_parser("show", help="Show current config")
    p_cfg_show.add_argument("--json", action="store_true")
    p_cfg_show.set_defaults(_handler="config_show")

    p_cfg_clear = cfg_subs.add_parser("clear", help="Delete local config file")
    p_cfg_clear.add_argument("--json", action="store_true")
    p_cfg_clear.set_defaults(_handler="config_clear")

    p_account = subs.add_parser(
        "account",
        help="Show API credit usage, upgrade options, and current plan status",
    )
    p_account.add_argument("--json", action="store_true")
    p_account.set_defaults(_handler="account_status")

    p_whoami = subs.add_parser("whoami", help="Show current CLI identity, key source, config paths, and plan context")
    p_whoami.add_argument("--json", action="store_true")
    p_whoami.set_defaults(_handler="whoami")

    p_doctor = subs.add_parser("doctor", help="Run CLI self-checks for config, credentials, and API validation")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.add_argument("--verbose", action="store_true", help="Show passing checks in addition to warnings/failures")
    p_doctor.set_defaults(_handler="doctor")

    p_logs = subs.add_parser("logs", help="Show local CLI activity logs")
    logs_subs = p_logs.add_subparsers(dest="logs_cmd", required=True)
    p_logs_path = logs_subs.add_parser("path", help="Show the local activity log file path")
    p_logs_path.add_argument("--json", action="store_true")
    p_logs_path.set_defaults(_handler="logs_path")

    p_logs_tail = logs_subs.add_parser("tail", help="Show recent CLI activity entries")
    p_logs_tail.add_argument("--limit", type=int, default=20)
    p_logs_tail.add_argument("--command", dest="log_command", help="Filter by command name")
    p_logs_tail.add_argument("--source", choices=["direct", "shell"], help="Filter by invocation source")
    p_logs_tail.add_argument("--json", action="store_true")
    p_logs_tail.set_defaults(_handler="logs_tail")

    p_completion = subs.add_parser("completion", help="Print shell completion snippets")
    p_completion.add_argument("shell", choices=["bash", "zsh", "fish"])
    p_completion.set_defaults(_handler="completion")

    p_plugins = subs.add_parser("plugins", help="Inspect the local CLI plugin directory")
    plugins_subs = p_plugins.add_subparsers(dest="plugins_cmd", required=True)
    p_plugins_dir = plugins_subs.add_parser("dir", help="Show the plugin directory path")
    p_plugins_dir.set_defaults(_handler="plugins_dir")
    p_plugins_list = plugins_subs.add_parser("list", help="List discovered plugin files")
    p_plugins_list.set_defaults(_handler="plugins_list")

    p_capabilities = subs.add_parser("capabilities", help="Print machine-readable CLI capabilities")
    p_capabilities.set_defaults(_handler="capabilities")

    p_shell = subs.add_parser("shell", help="Interactive shell with banner and command input field")
    p_shell.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable alternate-screen fullscreen mode (default: off, keeps scrollback).",
    )
    p_shell.set_defaults(_handler="shell")

    p_watch = subs.add_parser("watch", help="Refresh a report on an interval for a watchlist or asset")
    p_watch.add_argument("target", help="Watchlist name or asset symbol")
    p_watch.add_argument("--kind", choices=["watchlist", "stock", "crypto", "consensus"], default="watchlist")
    p_watch.add_argument("--asset", choices=["stocks", "crypto", "all"], default="stocks")
    _add_period_args(p_watch, default_days=7)
    p_watch.add_argument("--refresh", type=int, default=60, help="Seconds between refreshes")
    p_watch.add_argument("--iterations", type=int, default=0, help="Number of refresh cycles (0 = keep running)")
    p_watch.add_argument("--json", action="store_true")
    p_watch.set_defaults(_handler="watch")

    p_scan = subs.add_parser("scan", help="Run fast sentiment screeners for stocks or crypto")
    p_scan.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p_scan.add_argument("--style", choices=["starter", "daytrader", "swing", "investor"], help="Apply preset filters for your trading style")
    _add_period_args(p_scan, default_days=7)
    p_scan.add_argument("--limit", type=int, default=25, help="Source fetch limit per platform")
    p_scan.add_argument("--top", type=int, default=10, help="Rows to print in text mode")
    p_scan.add_argument("--min-buzz", type=float)
    p_scan.add_argument("--min-volume", type=int, help="Mentions for stocks/crypto, trade_count for polymarket")
    p_scan.add_argument("--min-platforms", type=int, help="Stocks only: minimum platform confirmations")
    p_scan.add_argument("--min-sentiment", type=float, help="Minimum sentiment filter (-1..1)")
    p_scan.add_argument("--max-sentiment", type=float, help="Maximum sentiment filter (-1..1)")
    p_scan.add_argument("--json", action="store_true")
    p_scan.set_defaults(_handler="scan")

    p_briefing = subs.add_parser("briefing", help="Profile-based market briefing for different investor styles")
    p_briefing.add_argument("--profile", choices=["starter", "daytrader", "swing", "investor", "crypto", "research", "portfolio"], default="starter")
    _add_period_args(p_briefing, default_days=7)
    p_briefing.add_argument("--limit", type=int, default=10)
    p_briefing.add_argument("--stocks", help="Optional focus watchlist tickers (comma-separated)")
    p_briefing.add_argument("--crypto", help="Optional focus crypto symbols (comma-separated)")
    p_briefing.add_argument("--from-watchlist", help="Merge symbols from local watchlist into focus sets")
    p_briefing.add_argument("--json", action="store_true")
    p_briefing.set_defaults(_handler="briefing")

    p_watchlist = subs.add_parser("watchlist", help="Manage local watchlists and run reports")
    wl_subs = p_watchlist.add_subparsers(dest="watchlist_cmd", required=True)

    p_wl_list = wl_subs.add_parser("list", help="List all watchlists")
    p_wl_list.add_argument("--json", action="store_true")
    p_wl_list.set_defaults(_handler="watchlist_list")

    p_wl_show = wl_subs.add_parser("show", help="Show one watchlist")
    p_wl_show.add_argument("name")
    p_wl_show.add_argument("--json", action="store_true")
    p_wl_show.set_defaults(_handler="watchlist_show")

    p_wl_add = wl_subs.add_parser("add", help="Add symbols to watchlist")
    p_wl_add.add_argument("name")
    p_wl_add.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p_wl_add.add_argument("--symbols", required=True, help="Comma-separated symbols")
    p_wl_add.add_argument("--json", action="store_true")
    p_wl_add.set_defaults(_handler="watchlist_add")

    p_wl_remove = wl_subs.add_parser("remove", help="Remove symbols from watchlist")
    p_wl_remove.add_argument("name")
    p_wl_remove.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p_wl_remove.add_argument("--symbols", required=True, help="Comma-separated symbols")
    p_wl_remove.add_argument("--json", action="store_true")
    p_wl_remove.set_defaults(_handler="watchlist_remove")

    p_wl_delete = wl_subs.add_parser("delete", help="Delete watchlist")
    p_wl_delete.add_argument("name")
    p_wl_delete.add_argument("--json", action="store_true")
    p_wl_delete.set_defaults(_handler="watchlist_delete")

    p_wl_report = wl_subs.add_parser("report", help="Run report for watchlist symbols")
    p_wl_report.add_argument("name")
    p_wl_report.add_argument("--asset", choices=["stocks", "crypto", "all"], default="stocks")
    _add_period_args(p_wl_report, default_days=7)
    p_wl_report.add_argument("--json", action="store_true")
    p_wl_report.set_defaults(_handler="watchlist_report")

    p_endpoint = subs.add_parser("endpoint", help="List/call every supported OpenAPI endpoint")
    ep_subs = p_endpoint.add_subparsers(dest="endpoint_cmd", required=True)

    p_ep_list = ep_subs.add_parser("list", help="List all endpoint IDs")
    p_ep_list.add_argument("--json", action="store_true")
    p_ep_list.set_defaults(_handler="endpoint_list")

    p_ep_call = ep_subs.add_parser("call", help="Call one endpoint by ID")
    p_ep_call.add_argument("endpoint_id", choices=sorted(ENDPOINTS.keys()))
    p_ep_call.add_argument("--ticker")
    p_ep_call.add_argument("--symbol")
    p_ep_call.add_argument("--q")
    p_ep_call.add_argument("--query")
    p_ep_call.add_argument("--tickers", help="Comma-separated tickers")
    p_ep_call.add_argument("--symbols", help="Comma-separated symbols")
    p_ep_call.add_argument("--assets", help="Generic comma-separated assets (for compare)")
    _add_period_args(p_ep_call, default_days=7)
    p_ep_call.add_argument("--limit", type=int)
    p_ep_call.add_argument("--offset", type=int)
    p_ep_call.add_argument("--include-inherited", action="store_true", help="Include inherited Reddit thread context for raw mention endpoints")
    p_ep_call.add_argument("--type", choices=["stock", "etf", "all"])
    p_ep_call.add_argument("--source", help="Optional canonical/alias news source filter for supported news endpoints")
    p_ep_call.add_argument("--json", action="store_true")
    p_ep_call.set_defaults(_handler="endpoint_call")

    p_stock = subs.add_parser("stock", help="Comprehensive stock report across News, Reddit, X, and Polymarket")
    p_stock.add_argument("ticker")
    _add_period_args(p_stock, default_days=7)
    p_stock.add_argument("--json", action="store_true")
    p_stock.set_defaults(_handler="stock_report")

    p_consensus = subs.add_parser("consensus", help="Cross-platform consensus report for a stock ticker")
    p_consensus.add_argument("ticker")
    _add_period_args(p_consensus, default_days=7)
    p_consensus.add_argument("--json", action="store_true")
    p_consensus.set_defaults(_handler="consensus_report")

    p_explain = subs.add_parser("explain", help="Narrative stock explanation tuned to a reader profile")
    p_explain.add_argument("ticker")
    _add_period_args(p_explain, default_days=7)
    p_explain.add_argument(
        "--profile",
        choices=["starter", "daytrader", "swing", "investor", "research"],
        default="investor",
    )
    p_explain.add_argument("--json", action="store_true")
    p_explain.set_defaults(_handler="explain_report")

    p_export = subs.add_parser("export", help="Render a report as json, markdown, or csv")
    p_export.add_argument("target", help="Ticker, symbol, or watchlist name")
    p_export.add_argument("--kind", choices=["stock", "crypto", "consensus", "watchlist"], required=True)
    p_export.add_argument("--asset", choices=["stocks", "crypto", "all"], default="stocks")
    _add_period_args(p_export, default_days=7)
    p_export.add_argument("--format", choices=["json", "md", "csv"], default="json")
    p_export.add_argument("--output-path", help="Optional file path to write instead of stdout")
    p_export.add_argument("--json", action="store_true")
    p_export.set_defaults(_handler="export")

    p_crypto = subs.add_parser("crypto", help="Comprehensive crypto report or pair comparison")
    p_crypto.add_argument("symbol_or_pair", help="Single symbol (BTC) or pair (BTC/ETH)")
    _add_period_args(p_crypto, default_days=7)
    p_crypto.add_argument("--json", action="store_true")
    p_crypto.set_defaults(_handler="crypto_report")

    p_ask = subs.add_parser("ask", help="Natural-language assistant mode")
    p_ask.add_argument("text", nargs="+")
    _add_period_args(p_ask, default_days=7)
    p_ask.add_argument("--json", action="store_true")
    p_ask.set_defaults(_handler="ask")

    p_trending = subs.add_parser("trending", help="Fetch trending lists")
    p_trending.add_argument("--platform", choices=["news-stocks", "reddit-stocks", "reddit-crypto", "x-stocks", "polymarket-stocks"], required=True)
    p_trending.add_argument("--dimension", choices=["main", "stocks", "sectors", "countries", "tokens"], default="main")
    _add_period_args(p_trending, default_days=1)
    p_trending.add_argument("--limit", type=int, default=20)
    p_trending.add_argument("--offset", type=int, default=0)
    p_trending.add_argument("--type", choices=["stock", "etf", "all"])
    p_trending.add_argument("--source", help="Optional canonical/alias news source filter")
    p_trending.add_argument("--json", action="store_true")
    p_trending.set_defaults(_handler="trending")

    p_search = subs.add_parser("search", help="Search assets by platform")
    p_search.add_argument("--platform", choices=["news-stocks", "reddit-stocks", "reddit-crypto", "x-stocks", "polymarket-stocks"], required=True)
    p_search.add_argument("query")
    _add_period_args(p_search, default_days=7)
    p_search.add_argument("--limit", type=int, default=20)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(_handler="search")

    p_compare = subs.add_parser("compare", help="Compare multiple assets")
    p_compare.add_argument("--platform", choices=["news-stocks", "reddit-stocks", "reddit-crypto", "x-stocks", "polymarket-stocks"], required=True)
    p_compare.add_argument("assets", help="Comma-separated assets")
    _add_period_args(p_compare, default_days=7)
    p_compare.add_argument("--json", action="store_true")
    p_compare.set_defaults(_handler="compare")

    p_stats = subs.add_parser("stats", help="Get stats endpoint by platform")
    p_stats.add_argument("--platform", choices=["news-stocks", "reddit-stocks", "reddit-crypto", "x-stocks", "polymarket-stocks"], required=True)
    p_stats.add_argument("--json", action="store_true")
    p_stats.set_defaults(_handler="stats")

    p_health = subs.add_parser("health", help="Get health endpoint by platform or all")
    p_health.add_argument("--platform", choices=["all", "root", "news-stocks", "reddit-stocks", "reddit-crypto", "x-stocks", "polymarket-stocks"], default="all")
    p_health.add_argument("--json", action="store_true")
    p_health.set_defaults(_handler="health")

    return parser


def _requires_api_key(args: Namespace) -> bool:
    handler = getattr(args, "_handler", "")
    if handler in {
        "onboard_guide",
        "onboard_wizard",
        "onboard_register",
        "onboard_redeem",
        "onboard_recover",
        "auth_login",
        "auth_logout",
        "auth_list",
        "auth_switch",
        "auth_current",
        "config_set",
        "config_show",
        "config_clear",
        "doctor",
        "whoami",
        "logs_path",
        "logs_tail",
        "completion",
        "plugins_dir",
        "plugins_list",
        "capabilities",
        "shell",
        "watchlist_list",
        "watchlist_show",
        "watchlist_add",
        "watchlist_remove",
        "watchlist_delete",
        "endpoint_list",
        "health",
    }:
        return False
    if handler == "endpoint_call":
        return not is_health_endpoint(args.endpoint_id)
    return True


def _call_and_emit_endpoint(
    client: Any,
    endpoint_id: str,
    args: Namespace,
    *,
    json_mode: bool,
    command: str,
    subcommand: str | None = None,
) -> None:
    data = invoke_endpoint(client, endpoint_id, args)
    payload = _endpoint_result_payload(endpoint_id, data, command=command, subcommand=subcommand)
    if json_mode:
        print_json(payload)
        return

    print(f"Endpoint: {endpoint_id}")
    print(f"Path: {ENDPOINTS[endpoint_id].path}")
    print_json(payload["data"])


def _run_health(client: Any, args: Namespace) -> None:
    if args.platform == "all":
        report = {}
        for endpoint_id in (
            "root.health",
            "news-stocks.health",
            "reddit-stocks.health",
            "reddit-crypto.health",
            "x-stocks.health",
            "polymarket-stocks.health",
        ):
            try:
                report[endpoint_id] = to_plain(invoke_endpoint(client, endpoint_id, args))
            except Exception as exc:  # pragma: no cover - defensive
                report[endpoint_id] = {"error": str(exc)}
        payload = with_json_metadata(
            {
                **report,
                "checks": report,
                "platform": "all",
                "platforms": list(report.keys()),
            },
            kind="multi_platform_health",
            command="health",
        )
        if args.json:
            print_json(payload)
        else:
            print_json(report)
        return

    endpoint_id = f"{args.platform}.health"
    _call_and_emit_endpoint(client, endpoint_id, args, json_mode=args.json, command="health")


def _run_trending(client: Any, args: Namespace) -> None:
    mapping = {
        ("news-stocks", "main"): "news-stocks.trending",
        ("news-stocks", "stocks"): "news-stocks.trending",
        ("news-stocks", "sectors"): "news-stocks.trending.sectors",
        ("news-stocks", "countries"): "news-stocks.trending.countries",
        ("reddit-stocks", "main"): "reddit-stocks.trending",
        ("reddit-stocks", "stocks"): "reddit-stocks.trending",
        ("reddit-stocks", "sectors"): "reddit-stocks.trending.sectors",
        ("reddit-stocks", "countries"): "reddit-stocks.trending.countries",
        ("reddit-crypto", "main"): "reddit-crypto.trending",
        ("reddit-crypto", "tokens"): "reddit-crypto.trending",
        ("x-stocks", "main"): "x-stocks.trending",
        ("x-stocks", "stocks"): "x-stocks.trending",
        ("x-stocks", "sectors"): "x-stocks.trending.sectors",
        ("x-stocks", "countries"): "x-stocks.trending.countries",
        ("polymarket-stocks", "main"): "polymarket-stocks.trending",
        ("polymarket-stocks", "stocks"): "polymarket-stocks.trending",
        ("polymarket-stocks", "sectors"): "polymarket-stocks.trending.sectors",
        ("polymarket-stocks", "countries"): "polymarket-stocks.trending.countries",
    }
    endpoint_id = mapping.get((args.platform, args.dimension))
    if endpoint_id is None:
        raise CliUsageError(f"Unsupported platform/dimension combination: {args.platform} + {args.dimension}")
    _call_and_emit_endpoint(client, endpoint_id, args, json_mode=args.json, command="trending")


def _run_search(client: Any, args: Namespace) -> None:
    endpoint_id = f"{args.platform}.search"
    call_args = Namespace(**vars(args))
    call_args.q = args.query
    _call_and_emit_endpoint(client, endpoint_id, call_args, json_mode=args.json, command="search")


def _run_compare(client: Any, args: Namespace) -> None:
    endpoint_id = f"{args.platform}.compare"
    call_args = Namespace(**vars(args))
    if args.platform == "reddit-crypto":
        call_args.symbols = args.assets
    else:
        call_args.tickers = args.assets
    _call_and_emit_endpoint(client, endpoint_id, call_args, json_mode=args.json, command="compare")


def _run_stats(client: Any, args: Namespace) -> None:
    endpoint_id = f"{args.platform}.stats"
    _call_and_emit_endpoint(client, endpoint_id, args, json_mode=args.json, command="stats")


def _scan_thresholds(args: Namespace) -> dict[str, Any]:
    thresholds: dict[str, Any] = {
        "min_buzz": args.min_buzz,
        "min_volume": args.min_volume,
        "min_platforms": args.min_platforms,
        "min_sentiment": args.min_sentiment,
        "max_sentiment": args.max_sentiment,
    }
    style = str(getattr(args, "style", "") or "").lower().strip()
    if not style:
        return thresholds

    if args.asset == "stocks":
        presets = {
            "starter": {"min_buzz": 55.0, "min_platforms": 1},
            "daytrader": {"min_buzz": 70.0, "min_volume": 150, "min_platforms": 2},
            "swing": {"min_buzz": 65.0, "min_volume": 90, "min_platforms": 2},
            "investor": {"min_buzz": 60.0, "min_volume": 250, "min_platforms": 2},
        }
    else:
        presets = {
            "starter": {"min_buzz": 55.0, "min_volume": 30},
            "daytrader": {"min_buzz": 65.0, "min_volume": 100},
            "swing": {"min_buzz": 60.0, "min_volume": 60},
            "investor": {"min_buzz": 58.0, "min_volume": 80},
        }

    preset = presets.get(style, {})
    for key, value in preset.items():
        if thresholds.get(key) is None:
            thresholds[key] = value
    return thresholds


def _run_scan(client: Any, args: Namespace) -> None:
    thresholds = _scan_thresholds(args)
    if args.asset == "stocks":
        report = build_stock_scan_report(client, **_period_from_args(args), limit=args.limit)
        rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
        if thresholds.get("min_buzz") is not None:
            rows = [row for row in rows if (row.get("consensus_buzz") or 0) >= thresholds["min_buzz"]]
        if thresholds.get("min_volume") is not None:
            rows = [row for row in rows if (row.get("total_volume") or 0) >= thresholds["min_volume"]]
        if thresholds.get("min_platforms") is not None:
            rows = [row for row in rows if (row.get("platforms") or 0) >= thresholds["min_platforms"]]
        if thresholds.get("min_sentiment") is not None:
            rows = [row for row in rows if (row.get("consensus_sentiment") or 0) >= thresholds["min_sentiment"]]
        if thresholds.get("max_sentiment") is not None:
            rows = [row for row in rows if (row.get("consensus_sentiment") or 0) <= thresholds["max_sentiment"]]
        rows = rows[: max(1, int(args.top))]
        report["rows"] = rows
        if args.style:
            report["style"] = args.style
            report["applied_filters"] = thresholds
        report["top"] = max(1, int(args.top))
        if args.json:
            print_json(report)
            return
        print(format_stock_scan_report(report, top=args.top))
        return

    report = build_crypto_scan_report(client, **_period_from_args(args), limit=args.limit)
    rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
    if thresholds.get("min_buzz") is not None:
        rows = [row for row in rows if (row.get("buzz_score") or 0) >= thresholds["min_buzz"]]
    if thresholds.get("min_volume") is not None:
        rows = [row for row in rows if (row.get("mentions") or 0) >= thresholds["min_volume"]]
    if thresholds.get("min_sentiment") is not None:
        rows = [row for row in rows if (row.get("sentiment") or 0) >= thresholds["min_sentiment"]]
    if thresholds.get("max_sentiment") is not None:
        rows = [row for row in rows if (row.get("sentiment") or 0) <= thresholds["max_sentiment"]]
    rows = rows[: max(1, int(args.top))]
    report["rows"] = rows
    if args.style:
        report["style"] = args.style
        report["applied_filters"] = thresholds
    report["top"] = max(1, int(args.top))
    if args.json:
        print_json(report)
        return
    print(format_crypto_scan_report(report, top=args.top))


def _run_briefing(client: Any, args: Namespace) -> None:
    stock_focus = csv_to_list(args.stocks) if args.stocks else []
    crypto_focus = csv_to_list(args.crypto) if args.crypto else []
    if getattr(args, "from_watchlist", None):
        watchlist = get_watchlist(args.from_watchlist)
        if watchlist is None:
            raise CliUsageError(f"Watchlist '{args.from_watchlist}' not found")
        for symbol in watchlist.get("stocks", []):
            if symbol not in stock_focus:
                stock_focus.append(symbol)
        for symbol in watchlist.get("crypto", []):
            if symbol not in crypto_focus:
                crypto_focus.append(symbol)

    report = build_market_briefing_report(
        client,
        profile=args.profile,
        **_period_from_args(args),
        limit=args.limit,
        stock_focus=stock_focus,
        crypto_focus=crypto_focus,
    )
    if args.json:
        print_json(report)
        return
    print(format_market_briefing_report(report))


def _handle_watchlist_without_api(args: Namespace) -> int:
    if args._handler == "watchlist_list":
        payload = list_watchlists()
        if args.json:
            print_json(
                with_json_metadata(
                    dict(payload),
                    kind="watchlist_catalog",
                    command="watchlist",
                    subcommand="list",
                    watchlists=payload,
                    count=len(payload),
                )
            )
        else:
            if not payload:
                print("No watchlists configured.")
            for name, data in payload.items():
                stocks = ", ".join(data.get("stocks", [])) or "-"
                crypto = ", ".join(data.get("crypto", [])) or "-"
                print(f"- {name}: stocks=[{stocks}] crypto=[{crypto}]")
        return 0

    if args._handler == "watchlist_show":
        payload = get_watchlist(args.name)
        if payload is None:
            raise CliUsageError(f"Watchlist '{args.name}' not found")
        if args.json:
            print_json(
                with_json_metadata(
                    {args.name: payload},
                    kind="watchlist_state",
                    command="watchlist",
                    subcommand="show",
                    name=args.name,
                    watchlist=payload,
                )
            )
        else:
            stocks = ", ".join(payload.get("stocks", [])) or "-"
            crypto = ", ".join(payload.get("crypto", [])) or "-"
            print(f"{args.name}:")
            print(f"  stocks: {stocks}")
            print(f"  crypto: {crypto}")
        return 0

    if args._handler == "watchlist_add":
        payload = upsert_watchlist_symbols(args.name, args.asset, args.symbols)
        if args.json:
            print_json(
                with_json_metadata(
                    {args.name: payload},
                    kind="watchlist_state",
                    command="watchlist",
                    subcommand="add",
                    name=args.name,
                    asset=args.asset,
                    watchlist=payload,
                )
            )
        else:
            print(f"Updated watchlist '{args.name}' ({args.asset}).")
        return 0

    if args._handler == "watchlist_remove":
        payload = remove_watchlist_symbols(args.name, args.asset, args.symbols)
        if args.json:
            print_json(
                with_json_metadata(
                    {args.name: payload},
                    kind="watchlist_state",
                    command="watchlist",
                    subcommand="remove",
                    name=args.name,
                    asset=args.asset,
                    watchlist=payload,
                )
            )
        else:
            print(f"Updated watchlist '{args.name}' ({args.asset}).")
        return 0

    if args._handler == "watchlist_delete":
        deleted = delete_watchlist(args.name)
        if args.json:
            print_json(
                with_json_metadata(
                    {"name": args.name, "deleted": deleted},
                    kind="watchlist_delete_result",
                    command="watchlist",
                    subcommand="delete",
                )
            )
        else:
            print(f"Deleted watchlist '{args.name}'." if deleted else f"Watchlist '{args.name}' not found.")
        return 0

    raise CliUsageError("Unknown watchlist command")


def _build_watchlist_report_payload(
    client: Any,
    *,
    name: str,
    asset: str,
    days: int | None,
    from_: str | None = None,
    to: str | None = None,
) -> dict[str, Any]:
    payload = get_watchlist(name)
    if payload is None:
        raise CliUsageError(f"Watchlist '{name}' not found")
    if days is None and not from_ and not to:
        days = 7

    report: dict[str, Any] = {
        "kind": "watchlist_report",
        "name": name,
        "asset": asset,
        "days": days,
        "from": from_,
        "to": to,
    }

    if asset == "all":
        stocks_symbols = payload.get("stocks", [])
        crypto_symbols = payload.get("crypto", [])
        if not stocks_symbols and not crypto_symbols:
            raise CliUsageError(f"Watchlist '{name}' has no symbols")
        report["symbols"] = {
            "stocks": stocks_symbols,
            "crypto": crypto_symbols,
        }
        if stocks_symbols:
            if len(stocks_symbols) == 1:
                report["stocks"] = build_stock_report(client, stocks_symbols[0], days=days, from_=from_, to=to)
            else:
                report["stocks"] = build_stock_compare_report(client, stocks_symbols[:10], days=days, from_=from_, to=to)
        if crypto_symbols:
            if len(crypto_symbols) == 1:
                report["crypto"] = build_crypto_report(client, crypto_symbols[0], days=days, from_=from_, to=to)
            else:
                report["crypto"] = build_crypto_compare_report(client, crypto_symbols[:10], days=days, from_=from_, to=to)
        return report

    symbols = payload.get(asset, [])
    if not symbols:
        raise CliUsageError(f"Watchlist '{name}' has no symbols in asset '{asset}'")

    report["symbols"] = list(symbols)
    if asset == "stocks":
        if len(symbols) == 1:
            report["report"] = build_stock_report(client, symbols[0], days=days, from_=from_, to=to)
            return report
        report["report"] = build_stock_compare_report(client, symbols[:10], days=days, from_=from_, to=to)
        return report

    if len(symbols) == 1:
        report["report"] = build_crypto_report(client, symbols[0], days=days, from_=from_, to=to)
        return report
    report["report"] = build_crypto_compare_report(client, symbols[:10], days=days, from_=from_, to=to)
    return report


def _format_watchlist_report_payload(report: dict[str, Any]) -> str:
    if report.get("kind") != "watchlist_report":
        return json.dumps(to_plain(report), indent=2, ensure_ascii=False)

    asset = str(report.get("asset") or "all")
    lines = [f"Watchlist report: {report.get('name', 'n/a')} [{asset}] ({report.get('days', 'n/a')}d)"]
    nested_report = report.get("report")
    if isinstance(nested_report, dict):
        lines.append("")
        if nested_report.get("kind") == "stock_report":
            lines.append(format_stock_report(nested_report))
        elif nested_report.get("kind") == "stock_compare":
            lines.append(format_stock_compare_report(nested_report))
        elif nested_report.get("kind") == "crypto_report":
            lines.append(format_crypto_report(nested_report))
        elif nested_report.get("kind") == "crypto_compare":
            lines.append(format_crypto_compare_report(nested_report))
        else:
            lines.append(json.dumps(to_plain(nested_report), indent=2, ensure_ascii=False))
        return "\n".join(lines)

    stocks_report = report.get("stocks")
    if isinstance(stocks_report, dict):
        lines.append("")
        if stocks_report.get("kind") == "stock_report":
            lines.append(format_stock_report(stocks_report))
        else:
            lines.append(format_stock_compare_report(stocks_report))
    crypto_report = report.get("crypto")
    if isinstance(crypto_report, dict):
        lines.append("")
        if crypto_report.get("kind") == "crypto_report":
            lines.append(format_crypto_report(crypto_report))
        else:
            lines.append(format_crypto_compare_report(crypto_report))
    return "\n".join(lines)


def _run_watchlist_report(client: Any, args: Namespace) -> None:
    report = _build_watchlist_report_payload(
        client,
        name=args.name,
        asset=args.asset,
        **_period_from_args(args),
    )
    if args.json:
        print_json(report)
        return
    print(_format_watchlist_report_payload(report))


def _run_stock_report(client: Any, args: Namespace) -> None:
    report = build_stock_report(client, args.ticker, **_period_from_args(args))
    if args.json:
        print_json(report)
        return
    print(format_stock_report(report))


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _resolve_report_volume(data: dict[str, Any], volume_key: str) -> Any:
    return data.get(volume_key)


def _extract_report_explanation(report: dict[str, Any], key: str) -> Any:
    payload = report.get(key)
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    return data.get("explanation")


def _build_consensus_report(report: dict[str, Any]) -> dict[str, Any]:
    source_specs = (
        ("news", "News", "mentions"),
        ("reddit", "Reddit", "mentions"),
        ("x", "X", "mentions"),
        ("polymarket", "Polymarket", "trade_count"),
    )
    sources: list[dict[str, Any]] = []
    buzz_values: list[float] = []
    sentiment_values: list[float] = []
    total_volume = 0

    for key, label, volume_key in source_specs:
        payload = report.get(key)
        if not isinstance(payload, dict) or not payload.get("ok"):
            sources.append(
                {
                    "source": key,
                    "label": label,
                    "ok": False,
                    "error": str((payload or {}).get("error") or "request failed"),
                }
            )
            continue

        data = payload.get("data")
        if not isinstance(data, dict):
            sources.append({"source": key, "label": label, "ok": False, "error": "no structured payload"})
            continue

        if data.get("found") is False:
            sources.append({"source": key, "label": label, "ok": True, "found": False})
            continue

        buzz = _as_float(data.get("buzz_score"))
        sentiment = _as_float(data.get("sentiment_score"))
        volume_raw = _resolve_report_volume(data, volume_key)
        volume = int(volume_raw) if isinstance(volume_raw, (int, float)) else 0
        trend = str(data.get("trend") or "n/a")

        if buzz is not None:
            buzz_values.append(buzz)
        if sentiment is not None:
            sentiment_values.append(sentiment)
        total_volume += volume

        sources.append(
            {
                "source": key,
                "label": label,
                "ok": True,
                "found": True,
                "buzz_score": buzz,
                "sentiment": sentiment,
                "volume": volume,
                "trend": trend,
            }
        )

    source_count = sum(1 for source in sources if source.get("found"))
    consensus_buzz = round(sum(buzz_values) / len(buzz_values), 2) if buzz_values else None
    consensus_sentiment = round(sum(sentiment_values) / len(sentiment_values), 3) if sentiment_values else None

    if consensus_sentiment is None:
        signal = "hot" if (consensus_buzz or 0) >= 70 and source_count >= 2 else "neutral"
    elif consensus_sentiment >= 0.12:
        signal = "bullish"
    elif consensus_sentiment <= -0.12:
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = min(
        99,
        int(
            round(
                min(source_count * 22, 55)
                + min(total_volume / 30, 20)
                + min(max((consensus_buzz or 0) - 45, 0) * 0.45, 14)
                + min(abs(consensus_sentiment or 0) * 100, 10)
            )
        ),
    )

    return {
        "kind": "consensus_report",
        "ticker": report.get("ticker"),
        "days": report.get("days"),
        "consensus_buzz": consensus_buzz,
        "consensus_sentiment": consensus_sentiment,
        "signal": signal,
        "confidence": confidence,
        "sources_covered": source_count,
        "total_volume": total_volume,
        "sources": sources,
        "reddit_explanation": _extract_report_explanation(report, "reddit_explain"),
        "x_explanation": _extract_report_explanation(report, "x_explain"),
    }


def _format_consensus_report(payload: dict[str, Any]) -> str:
    lines = [
        f"Consensus for {payload.get('ticker', 'n/a')} ({payload.get('days', 'n/a')}d)",
        (
            f"- Signal: {payload.get('signal', 'n/a')} | confidence={payload.get('confidence', 'n/a')} "
            f"| buzz={payload.get('consensus_buzz', 'n/a')} | sentiment={payload.get('consensus_sentiment', 'n/a')}"
        ),
        f"- Cross-source coverage: {payload.get('sources_covered', 0)} sources, volume={payload.get('total_volume', 0)}",
    ]
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        if not source.get("ok"):
            lines.append(f"- {source.get('label', source.get('source', 'source'))}: unavailable ({source.get('error', 'request failed')})")
            continue
        if not source.get("found"):
            lines.append(f"- {source.get('label', source.get('source', 'source'))}: no data in selected window")
            continue
        lines.append(
            f"- {source.get('label', source.get('source', 'source'))}: "
            f"buzz={source.get('buzz_score', 'n/a')}, sentiment={source.get('sentiment', 'n/a')}, "
            f"volume={source.get('volume', 0)}, trend={source.get('trend', 'n/a')}"
        )
    reddit_explanation = str(payload.get("reddit_explanation") or "").strip()
    if reddit_explanation:
        lines.append(f"- Reddit context: {reddit_explanation}")
    x_explanation = str(payload.get("x_explanation") or "").strip()
    if x_explanation:
        lines.append(f"- X/Twitter context: {x_explanation}")
    return "\n".join(lines)


def _run_consensus_report(client: Any, args: Namespace) -> None:
    stock_report = build_stock_report(client, args.ticker, **_period_from_args(args))
    payload = _build_consensus_report(stock_report)
    if args.json:
        print_json(payload)
        return
    print(_format_consensus_report(payload))


def _build_explain_report(consensus: dict[str, Any], *, reader_profile: str) -> dict[str, Any]:
    profile_frames = {
        "starter": "Focus on the headline signal and avoid overreacting to a single noisy source.",
        "daytrader": "Treat this as a short-horizon momentum read; cross-source confirmation matters more than raw narrative.",
        "swing": "Look for follow-through across multiple sessions rather than a one-day spike.",
        "investor": "Use the cross-source blend as a durability check, not a standalone investment thesis.",
        "research": "Pay attention to source gaps, missing data, and whether the signal is narrative-heavy or volume-backed.",
    }
    signal = str(consensus.get("signal") or "neutral")
    confidence = int(consensus.get("confidence") or 0)
    buzz = consensus.get("consensus_buzz")
    sentiment = consensus.get("consensus_sentiment")
    ticker = consensus.get("ticker")

    if signal == "bullish":
        headline = f"{ticker} is reading bullish across the tracked channels."
    elif signal == "bearish":
        headline = f"{ticker} is reading bearish across the tracked channels."
    elif signal == "hot":
        headline = f"{ticker} has unusually strong attention, but directional sentiment is still mixed."
    else:
        headline = f"{ticker} is broadly neutral right now, with no strong directional consensus."

    evidence = (
        f"Coverage spans {consensus.get('sources_covered', 0)} sources, "
        f"with total tracked volume {consensus.get('total_volume', 0)}, "
        f"consensus buzz {buzz}, sentiment {sentiment}, and confidence {confidence}."
    )
    reddit_context = str(consensus.get("reddit_explanation") or "").strip()
    if not reddit_context:
        reddit_context = "No extra Reddit explanation was available."
    x_context = str(consensus.get("x_explanation") or "").strip()
    if not x_context:
        x_context = "No extra X/Twitter explanation was available."

    return {
        "kind": "explain_report",
        "ticker": ticker,
        "days": consensus.get("days"),
        "profile": reader_profile,
        "signal": signal,
        "confidence": confidence,
        "headline": headline,
        "evidence": evidence,
        "profile_guidance": profile_frames[reader_profile],
        "reddit_context": reddit_context,
        "x_context": x_context,
        "consensus": consensus,
    }


def _format_explain_report(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Explain {payload.get('ticker', 'n/a')} for {payload.get('profile', 'n/a')} ({payload.get('days', 'n/a')}d)",
            f"- Headline: {payload.get('headline', 'n/a')}",
            f"- Evidence: {payload.get('evidence', 'n/a')}",
            f"- Profile lens: {payload.get('profile_guidance', 'n/a')}",
            f"- Reddit context: {payload.get('reddit_context', 'n/a')}",
            f"- X/Twitter context: {payload.get('x_context', 'n/a')}",
        ]
    )


def _run_explain_report(client: Any, args: Namespace) -> None:
    stock_report = build_stock_report(client, args.ticker, **_period_from_args(args))
    consensus = _build_consensus_report(stock_report)
    payload = _build_explain_report(consensus, reader_profile=args.profile)
    if args.json:
        print_json(payload)
        return
    print(_format_explain_report(payload))


def _build_named_report(
    client: Any,
    *,
    kind: str,
    target: str,
    days: int | None,
    from_: str | None = None,
    to: str | None = None,
    asset: str = "stocks",
) -> dict[str, Any]:
    if kind == "stock":
        return build_stock_report(client, target, days=days, from_=from_, to=to)
    if kind == "crypto":
        symbols = csv_to_list(target.upper().replace("/", ","))
        if len(symbols) >= 2:
            return build_crypto_compare_report(client, symbols[:10], days=days, from_=from_, to=to)
        if not symbols:
            raise CliUsageError("Provide a crypto symbol like BTC or a pair like BTC/ETH")
        return build_crypto_report(client, symbols[0], days=days, from_=from_, to=to)
    if kind == "consensus":
        return _build_consensus_report(build_stock_report(client, target, days=days, from_=from_, to=to))
    if kind == "watchlist":
        return _build_watchlist_report_payload(client, name=target, asset=asset, days=days, from_=from_, to=to)
    raise CliUsageError(f"Unsupported report kind: {kind}")


def _format_named_report(kind: str, payload: dict[str, Any]) -> str:
    if kind == "stock":
        return format_stock_report(payload)
    if kind == "crypto":
        if payload.get("kind") == "crypto_compare":
            return format_crypto_compare_report(payload)
        return format_crypto_report(payload)
    if kind == "consensus":
        return _format_consensus_report(payload)
    if kind == "watchlist":
        return _format_watchlist_report_payload(payload)
    raise CliUsageError(f"Unsupported report kind: {kind}")


def _render_csv(kind: str, payload: dict[str, Any]) -> str:
    rows: list[dict[str, Any]]
    if kind == "consensus":
        rows = [
            {
                "source": row.get("source"),
                "label": row.get("label"),
                "ok": row.get("ok"),
                "found": row.get("found"),
                "buzz_score": row.get("buzz_score"),
                "sentiment": row.get("sentiment"),
                "volume": row.get("volume"),
                "trend": row.get("trend"),
            }
            for row in payload.get("sources", [])
            if isinstance(row, dict)
        ]
    elif kind == "stock":
        rows = []
        for source_name, volume_key in (
            ("news", "mentions"),
            ("reddit", "mentions"),
            ("x", "mentions"),
            ("polymarket", "trade_count"),
        ):
            source_payload = payload.get(source_name)
            if not isinstance(source_payload, dict) or not source_payload.get("ok"):
                continue
            data = source_payload.get("data")
            if not isinstance(data, dict):
                continue
            rows.append(
                {
                    "source": source_name,
                    "ticker": payload.get("ticker"),
                    "buzz_score": data.get("buzz_score"),
                    "sentiment": data.get("sentiment_score"),
                    "volume": _resolve_report_volume(data, volume_key),
                    "trend": data.get("trend"),
                }
            )
    else:
        raise CliUsageError(f"CSV export is not supported for kind '{kind}'")

    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _write_or_print_rendered(content: str, *, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        print(output_path)
        return
    print(content, end="" if content.endswith("\n") else "\n")


def _run_export(client: Any, args: Namespace) -> None:
    report = _build_named_report(
        client,
        kind=args.kind,
        target=args.target,
        **_period_from_args(args),
        asset=getattr(args, "asset", "stocks"),
    )
    if args.format == "json":
        rendered = json.dumps(to_plain(report), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    elif args.format == "md":
        rendered = _format_named_report(args.kind, report) + "\n"
    else:
        rendered = _render_csv(args.kind, report)
    _write_or_print_rendered(rendered, output_path=args.output_path)


def _run_watch(client: Any, args: Namespace) -> None:
    if args.refresh < 1:
        raise CliUsageError("--refresh must be at least 1 second")
    if args.iterations < 0:
        raise CliUsageError("--iterations must be 0 or greater")

    snapshots: list[dict[str, Any]] = []
    iteration = 0
    while True:
        iteration += 1
        report = _build_named_report(
            client,
            kind=args.kind,
            target=args.target,
            **_period_from_args(args),
            asset=getattr(args, "asset", "stocks"),
        )
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if args.json:
            snapshots.append({"captured_at": timestamp, "report": report})
        else:
            if iteration > 1:
                print("")
            print(f"[{timestamp}] refresh {iteration}")
            print(_format_named_report(args.kind, report))

        if args.iterations and iteration >= args.iterations:
            break
        if not args.iterations and not sys.stdout.isatty():
            break
        time.sleep(args.refresh)

    if args.json:
        print_json(
            {
                "kind": "watch",
                "target": args.target,
                "report_kind": args.kind,
                "refresh_seconds": args.refresh,
                "iterations": len(snapshots),
                "snapshots": snapshots,
            }
        )


def _run_crypto_report(client: Any, args: Namespace) -> None:
    raw = args.symbol_or_pair.strip().upper().replace("/", ",")
    symbols = csv_to_list(raw)

    if len(symbols) >= 2:
        report = build_crypto_compare_report(client, symbols[:10], **_period_from_args(args))
        if args.json:
            print_json(report)
            return
        print(format_crypto_compare_report(report))
        return

    if not symbols:
        raise CliUsageError("Provide a crypto symbol like BTC or a pair like BTC/ETH")

    report = build_crypto_report(client, symbols[0], **_period_from_args(args))
    if args.json:
        print_json(report)
        return
    print(format_crypto_report(report))


def _iter_stock_search_hits(client: Any, query: str):
    for source, fn in (
        ("reddit", client.reddit.search),
        ("x", client.x.search),
        ("polymarket", client.polymarket.search),
    ):
        try:
            payload = to_plain(fn(query))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        for row in results:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            yield source, row


def _score_stock_hit(query: str, row: dict[str, Any]) -> int:
    q = query.strip().upper()
    ticker = str(row.get("ticker") or "").strip().upper()
    name = str(row.get("name") or "").strip().upper()
    aliases_raw = row.get("aliases") or []
    aliases = [str(alias).strip().upper() for alias in aliases_raw if str(alias).strip()]

    if ticker == q:
        return 140
    if name and name == q:
        return 130
    if any(alias == q for alias in aliases):
        return 130
    if name and q in name:
        return 115
    if any(q in alias for alias in aliases):
        return 115
    if ticker.startswith(q) and len(q) >= 2:
        return 70
    return 0


def _resolve_stock_ticker(client: Any, text: str, primary: str | None) -> tuple[str | None, str | None, str | None]:
    candidates: list[str] = []
    if primary:
        candidates.append(primary.upper().replace("$", ""))
    candidates.extend(extract_terms(text))

    seen: set[str] = set()
    queries: list[str] = []
    for token in candidates:
        normalized = token.strip().upper().replace("$", "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(normalized)

    best: tuple[int, str, str, str] | None = None
    for query in queries[:8]:
        for source, row in _iter_stock_search_hits(client, query):
            score = _score_stock_hit(query, row)
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            if best is None or score > best[0]:
                best = (score, ticker, query, source)

    if best and best[0] >= 110:
        return best[1], best[2], best[3]

    if primary:
        fallback = primary.upper().replace("$", "").strip()
        if fallback and fallback.isalnum() and len(fallback) <= 10:
            return fallback, None, None

    return None, None, None


def _run_ask(client: Any, args: Namespace) -> None:
    text = " ".join(args.text).strip()
    intent = parse_ask_intent(text)

    if intent.kind == "briefing_report":
        brief_args = Namespace(
            profile=(intent.primary or "starter"),
            days=args.days,
            from_=getattr(args, "from_", None),
            to=getattr(args, "to", None),
            limit=10,
            stocks=None,
            crypto=None,
            from_watchlist=None,
            json=args.json,
        )
        _run_briefing(client, brief_args)
        return

    if intent.kind == "scan_report":
        asset = (intent.primary or "stocks").lower()
        if asset == "all":
            payload = {
                "kind": "scan_bundle",
                "days": args.days,
                "from": getattr(args, "from_", None),
                "to": getattr(args, "to", None),
                "stocks": build_stock_scan_report(client, **_period_from_args(args), limit=25),
                "crypto": build_crypto_scan_report(client, **_period_from_args(args), limit=25),
            }
            if args.json:
                print_json(payload)
                return
            print("Combined scan report")
            print("")
            print(format_stock_scan_report(payload["stocks"], top=8))
            print("")
            print(format_crypto_scan_report(payload["crypto"], top=8))
            return

        scan_args = Namespace(
            asset=asset,
            style=None,
            days=args.days,
            from_=getattr(args, "from_", None),
            to=getattr(args, "to", None),
            limit=25,
            top=10,
            min_buzz=None,
            min_volume=None,
            min_platforms=None,
            min_sentiment=None,
            max_sentiment=None,
            json=args.json,
        )
        _run_scan(client, scan_args)
        return

    if intent.kind == "watchlist_report":
        watchlist_args = Namespace(
            name=(intent.primary or "core"),
            asset=(intent.secondary or "all").lower(),
            days=args.days,
            from_=getattr(args, "from_", None),
            to=getattr(args, "to", None),
            json=args.json,
        )
        _run_watchlist_report(client, watchlist_args)
        return

    if intent.kind == "trending_report":
        asset = "crypto" if (intent.primary or "").lower() == "crypto" else "stocks"
        report = build_trending_report(client, asset=asset, **_period_from_args(args), limit=5)
        if args.json:
            print_json(report)
            return
        print(format_trending_report(report))
        return

    if intent.kind == "stock_compare" and intent.primary and intent.secondary:
        first, first_from, _ = _resolve_stock_ticker(client, intent.primary, intent.primary)
        second, second_from, _ = _resolve_stock_ticker(client, intent.secondary, intent.secondary)
        tickers = [first or intent.primary, second or intent.secondary]
        report = build_stock_compare_report(client, tickers, **_period_from_args(args))
        if args.json:
            report["resolution"] = {
                "first": {"input": intent.primary, "query": first_from or intent.primary, "ticker": tickers[0]},
                "second": {"input": intent.secondary, "query": second_from or intent.secondary, "ticker": tickers[1]},
            }
            print_json(report)
            return
        if tickers[0] != intent.primary.upper():
            print(f"Resolved '{intent.primary.upper()}' -> {tickers[0]}")
        if tickers[1] != intent.secondary.upper():
            print(f"Resolved '{intent.secondary.upper()}' -> {tickers[1]}")
        print(format_stock_compare_report(report))
        return

    if intent.kind == "stock_report" and intent.primary:
        resolved_ticker, resolved_from, resolved_source = _resolve_stock_ticker(client, text, intent.primary)
        ticker = resolved_ticker or intent.primary
        report = build_stock_report(client, ticker, **_period_from_args(args))
        if args.json:
            if resolved_from and resolved_source:
                report["resolution"] = {
                    "input": intent.primary,
                    "query": resolved_from,
                    "ticker": ticker,
                    "source": resolved_source,
                }
            print_json(report)
            return
        if resolved_from and resolved_source and ticker != intent.primary:
            print(f"Resolved '{resolved_from}' -> {ticker} via {resolved_source} search")
        print(format_stock_report(report))
        return

    if intent.kind == "crypto_report" and intent.primary:
        report = build_crypto_report(client, intent.primary, **_period_from_args(args))
        if args.json:
            print_json(report)
            return
        print(format_crypto_report(report))
        return

    if intent.kind == "crypto_compare" and intent.primary and intent.secondary:
        report = build_crypto_compare_report(client, [intent.primary, intent.secondary], **_period_from_args(args))
        if args.json:
            print_json(report)
            return
        print(format_crypto_compare_report(report))
        return

    report = build_search_fallback_report(client, text)
    if args.json:
        print_json(report)
        return
    print(format_search_fallback_report(report))


def _handle_auth(args: Namespace) -> int:
    return handle_auth_command(args)


def _handle_config(args: Namespace) -> int:
    return handle_config_command(args)


def _invocation_command_name(raw_argv: list[str]) -> str | None:
    normalized_argv = _normalize_global_cli_flags(raw_argv)
    for token in normalized_argv:
        if token.startswith("-"):
            continue
        return token.lower()
    return None


def _should_record_activity(raw_argv: list[str]) -> bool:
    command = _invocation_command_name(raw_argv)
    return bool(command) and command not in {"logs"}


def _main_impl(raw_argv: list[str], *, argv_supplied: bool) -> int:
    parser = _build_parser()
    normalized_argv = _normalize_global_cli_flags(raw_argv)
    try:
        args = parser.parse_args(normalized_argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return code
    setattr(args, "json", should_output_json(args, argv_supplied=argv_supplied))

    if args.version:
        if args.json:
            print_json({"kind": "version", "command": "version", "name": "adanos-cli", "version": __version__})
        else:
            print(f"adanos-cli {__version__}")
        return 0

    runtime_cfg = resolve_runtime_config(
        api_key_override=getattr(args, "api_key", None),
        base_url_override=getattr(args, "base_url", None),
    )

    if not getattr(args, "command", None):
        is_tty = bool(sys.stdin.isatty() and sys.stdout.isatty())
        if args.json:
            payload = _capabilities_payload(runtime_cfg.base_url, has_api_key=bool(runtime_cfg.api_key))
            payload["mode"] = "welcome"
            print_json(payload)
        elif is_tty:
            _print_start_screen(
                runtime_cfg.base_url,
                has_api_key=bool(runtime_cfg.api_key),
                api_key=runtime_cfg.api_key,
            )
            _print_update_notice_if_available()
        else:
            _print_welcome_screen(runtime_cfg.base_url, has_api_key=bool(runtime_cfg.api_key))
        return 0

    if getattr(args, "command", "") in {"auth", "login", "logout"}:
        try:
            return _handle_auth(args)
        except (CliUsageError, ValueError) as exc:
            _emit_error(
                json_mode=args.json,
                code="auth_error",
                message=str(exc),
            )
            return 2

    if getattr(args, "command", "") == "config":
        try:
            return _handle_config(args)
        except CliUsageError as exc:
            _emit_error(
                json_mode=args.json,
                code="config_error",
                message=str(exc),
            )
            return 2

    if getattr(args, "command", "") == "watchlist" and getattr(args, "_handler", "") in {
        "watchlist_list",
        "watchlist_show",
        "watchlist_add",
        "watchlist_remove",
        "watchlist_delete",
    }:
        try:
            return _handle_watchlist_without_api(args)
        except (CliUsageError, ValueError) as exc:
            _emit_error(
                json_mode=args.json,
                code="watchlist_error",
                message=str(exc),
            )
            return 2

    handler = getattr(args, "_handler", "")
    if handler == "capabilities":
        payload = _capabilities_payload(runtime_cfg.base_url, has_api_key=bool(runtime_cfg.api_key))
        if args.json:
            print_json(payload)
        else:
            _print_capabilities_text(payload)
        return 0

    if handler == "whoami":
        return _run_whoami(runtime_cfg, json_mode=args.json)

    if handler == "doctor":
        return _run_doctor(runtime_cfg, json_mode=args.json, verbose=bool(getattr(args, "verbose", False)))

    if handler == "logs_path":
        return _run_logs_path(json_mode=args.json)

    if handler == "logs_tail":
        return _run_logs_tail(args, json_mode=args.json)

    if handler == "completion":
        script = _completion_script(args.shell)
        print(script, end="")
        return 0

    if handler == "plugins_dir":
        payload = {
            "ok": True,
            "kind": "plugins_dir",
            "command": "plugins",
            "subcommand": "dir",
            "path": str(_plugins_dir()),
        }
        if args.json:
            print_json(payload)
        else:
            print(payload["path"])
        return 0

    if handler == "plugins_list":
        payload = {
            "ok": True,
            "kind": "plugins_list",
            "command": "plugins",
            "subcommand": "list",
            "path": str(_plugins_dir()),
            "plugins": _list_plugin_files(),
        }
        if args.json:
            print_json(payload)
        else:
            if not payload["plugins"]:
                print("No plugins discovered.")
            else:
                for plugin in payload["plugins"]:
                    print(f"{plugin['name']}: {plugin['path']}")
        return 0

    if handler == "shell":
        return _run_shell(
            runtime_cfg.base_url,
            has_api_key=bool(runtime_cfg.api_key),
            use_fullscreen=_resolve_shell_fullscreen(getattr(args, "fullscreen", None)),
            api_key=runtime_cfg.api_key,
        )

    if handler == "onboard_guide":
        if args.json:
            print_json(
                with_json_metadata(
                    {
                        "ok": True,
                        "onboarding": {
                            "base_url": runtime_cfg.base_url,
                            "steps": [
                                "adanos onboard wizard",
                                'adanos onboard register --name "Your Name" --email "you@example.com" --purpose "CLI usage for stocks and crypto"',
                                "check email for the one-time token",
                                "adanos onboard redeem --token <delivery_token> --save",
                                'adanos onboard recover --email "you@example.com"',
                            ],
                        },
                    },
                    kind="onboarding_guide",
                    command="onboard",
                    subcommand="guide",
                )
            )
        else:
            _print_onboarding_guide(runtime_cfg.base_url, has_api_key=bool(runtime_cfg.api_key))
        return 0

    if handler == "onboard_wizard":
        return _run_onboard_wizard(
            args,
            runtime_cfg.base_url,
            json_mode=args.json,
            runtime_has_key=bool(runtime_cfg.api_key),
        )

    if handler == "onboard_register":
        return _run_onboard_register(args, runtime_cfg.base_url, json_mode=args.json)

    if handler == "onboard_redeem":
        return _run_onboard_redeem(args, runtime_cfg.base_url, json_mode=args.json)

    if handler == "onboard_recover":
        return _run_onboard_recover(args, json_mode=args.json)

    if _requires_api_key(args) and not runtime_cfg.api_key:
        if args.json:
            _emit_error(
                json_mode=True,
                code="api_key_missing",
                message="API key is not configured",
                hint="Run `adanos onboard` or `adanos config set --api-key sk_live_xxx`",
            )
        else:
            _print_onboarding_guide(runtime_cfg.base_url)
        return 2

    if handler == "account_status":
        return _run_account_status(
            args,
            runtime_cfg.base_url,
            runtime_cfg.api_key or "",
            json_mode=args.json,
        )

    if handler == "endpoint_list":
        endpoints = [
            with_json_metadata(
                {
                    "id": spec.endpoint_id,
                    "path": spec.path,
                    "description": spec.description,
                    "required": list(spec.required_params),
                    "optional": list(spec.optional_params),
                },
                kind="endpoint_spec",
                command="endpoint",
                subcommand="list",
            )
            for spec in list_endpoints()
        ]
        if args.json:
            print_json(endpoints)
        else:
            print(f"Supported OpenAPI endpoints: {len(endpoints)}")
            for spec in endpoints:
                req = f" required={','.join(spec['required'])}" if spec["required"] else ""
                opt = f" optional={','.join(spec['optional'])}" if spec["optional"] else ""
                print(f"- {spec['id']}: {spec['path']}{req}{opt}")
        return 0

    client = None

    try:
        StockSentimentClient = _load_sdk_client_class()
        client = StockSentimentClient(api_key=runtime_cfg.api_key or "", base_url=runtime_cfg.base_url)

        if handler == "endpoint_call":
            _call_and_emit_endpoint(
                client,
                args.endpoint_id,
                args,
                json_mode=args.json,
                command="endpoint",
                subcommand="call",
            )
            return 0

        if handler == "stock_report":
            _run_stock_report(client, args)
            return 0

        if handler == "consensus_report":
            _run_consensus_report(client, args)
            return 0

        if handler == "explain_report":
            _run_explain_report(client, args)
            return 0

        if handler == "export":
            _run_export(client, args)
            return 0

        if handler == "watch":
            _run_watch(client, args)
            return 0

        if handler == "crypto_report":
            _run_crypto_report(client, args)
            return 0

        if handler == "ask":
            _run_ask(client, args)
            return 0

        if handler == "trending":
            _run_trending(client, args)
            return 0

        if handler == "search":
            _run_search(client, args)
            return 0

        if handler == "compare":
            _run_compare(client, args)
            return 0

        if handler == "stats":
            _run_stats(client, args)
            return 0

        if handler == "scan":
            _run_scan(client, args)
            return 0

        if handler == "briefing":
            _run_briefing(client, args)
            return 0

        if handler == "watchlist_report":
            _run_watchlist_report(client, args)
            return 0

        if handler == "health":
            _run_health(client, args)
            return 0

        raise CliUsageError("Unsupported command")

    except CliUsageError as exc:
        _emit_error(
            json_mode=args.json,
            code="usage_error",
            message=str(exc),
            hint="Run `adanos --help` or `adanos --output json capabilities`",
        )
        return 2
    except Exception as exc:  # pragma: no cover - top-level safeguard
        code, message, hint, status_code = _classify_runtime_error(exc)
        _emit_error(
            json_mode=args.json,
            code=code,
            message=message,
            hint=hint,
            status_code=status_code,
        )
        return 1
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def main(argv: list[str] | None = None, *, invocation_source: str = "direct") -> int:
    argv_supplied = argv is not None
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    started = time.monotonic()
    exit_code = _main_impl(raw_argv, argv_supplied=argv_supplied)
    if _should_record_activity(raw_argv):
        try:
            append_activity(
                raw_argv,
                source=invocation_source,
                exit_code=exit_code,
                duration_ms=int(round((time.monotonic() - started) * 1000)),
            )
        except Exception:
            pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
