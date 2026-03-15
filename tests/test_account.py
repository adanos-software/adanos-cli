"""Account status and quota UX tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import respx


import adanos_cli.main as cli_main


@respx.mock
def test_account_status_free_plan_json(capsys) -> None:
    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 123},
            headers={
                "X-Account-Type": "free",
                "X-RateLimit-Limit-Monthly": "250",
                "X-RateLimit-Remaining-Monthly": "200",
                "X-RateLimit-Used-Monthly": "50",
            },
        )
    )

    rc = cli_main.main(["--api-key", "adanos_key_test", "account", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["kind"] == "account_status"
    assert payload["command"] == "account"
    assert payload["account_type"] == "free"
    assert payload["monthly_limit"] == 250
    assert payload["monthly_used"] == 50
    assert payload["monthly_remaining"] == 200
    assert payload["status"] == "active"
    assert payload["upgrade_options"] == ["hobby", "professional"]


@respx.mock
def test_account_status_success_text_does_not_print_stats_note(capsys) -> None:
    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 420970, "unique_tickers": 5770},
            headers={
                "X-Account-Type": "free",
                "X-RateLimit-Limit-Monthly": "250",
                "X-RateLimit-Remaining-Monthly": "200",
                "X-RateLimit-Used-Monthly": "50",
            },
        )
    )

    rc = cli_main.main(["--api-key", "adanos_key_test", "account"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "- Note:" not in out


@respx.mock
def test_account_status_professional_plan_json(capsys) -> None:
    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            200,
            json={"total_mentions": 987},
            headers={
                "X-Account-Type": "professional",
                "X-RateLimit-Limit-Monthly": "unlimited",
                "X-RateLimit-Remaining-Monthly": "unlimited",
                "X-RateLimit-Used-Monthly": "120",
            },
        )
    )

    rc = cli_main.main(["--api-key", "adanos_key_test", "account", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["command"] == "account"
    assert payload["account_type"] == "professional"
    assert payload["paid_active"] is True
    assert payload["monthly_limit"] is None
    assert payload["status"] == "paid_active"
    assert payload["upgrade_options"] == []


@respx.mock
def test_account_status_out_of_credits_text(capsys) -> None:
    respx.get("https://api.adanos.org/reddit/stocks/v1/stats").mock(
        return_value=httpx.Response(
            429,
            json={
                "detail": {
                    "error": "Monthly API limit exceeded",
                    "message": "You have exceeded your free tier limit of 250 requests per month.",
                    "limit": 250,
                    "used": 250,
                    "account_type": "free",
                }
            },
            headers={
                "X-RateLimit-Limit": "250",
                "X-RateLimit-Remaining": "0",
            },
        )
    )

    rc = cli_main.main(["--api-key", "adanos_key_test", "account"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Status: out of API credits" in out
    assert "Upgrade options: hobby, professional" in out


def test_classify_runtime_error_monthly_quota() -> None:
    class _QuotaError(Exception):
        pass

    exc = _QuotaError(
        "Unexpected status code: 429\n\nResponse content:\n"
        '{"detail":{"error":"Monthly API limit exceeded","message":"free tier limit"}}'
    )
    code, message, hint, status_code = cli_main._classify_runtime_error(exc)
    assert code == "out_of_api_credits"
    assert "Out of API credits" in message
    assert hint is not None and "adanos account" in hint
    assert status_code == 429
