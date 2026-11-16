"""Run the CLI against a local HTTP server with API 1.55 response contracts."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import sys
from threading import Thread
from urllib.parse import urlparse, parse_qs

import pytest


@pytest.fixture
def api_server():
    state = {"status": 200, "payload": {}, "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["paths"].append(self.path)
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(state["payload"]).encode())

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", state
        finally:
            server.shutdown()
            thread.join()


def run_cli(base_url, tmp_path, *args):
    env = {**os.environ, "ADANOS_API_KEY": "test-key", "ADANOS_BASE_URL": base_url,
           "ADANOS_CLI_DISABLE_UPDATE_CHECK": "1", "XDG_CONFIG_HOME": str(tmp_path / "config")}
    result = subprocess.run(
        [sys.executable, "-m", "adanos_cli", "--json", *args],
        env=env, text=True, capture_output=True, timeout=20,
    )
    (tmp_path / "cli-result.json").write_text(json.dumps({
        "command": [sys.executable, "-m", "adanos_cli", "--json", *args],
        "base_url": base_url, "returncode": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
    }, indent=2))
    return result


@pytest.mark.parametrize("status,payload,message", [
    (404, {"detail": {"error_code": "unsupported_ticker", "message": "Unsupported ticker BK."}}, "Unsupported ticker BK."),
    (422, {"detail": [{"loc": ["path", "ticker"], "msg": "Invalid Graph key", "type": "string_pattern_mismatch"}]}, "Invalid Graph key"),
    (503, {"detail": "Polymarket identity lookup unavailable"}, "Polymarket identity lookup unavailable"),
])
def test_polymarket_errors_exit_nonzero_without_success_output(api_server, tmp_path, status, payload, message):
    base_url, state = api_server
    state.update(status=status, payload=payload)
    result = run_cli(base_url, tmp_path, "endpoint", "call", "polymarket-stocks.stock.mentions", "--ticker", "BK")
    assert result.returncode != 0
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert message in error["error"]["message"]
    assert urlparse(state["paths"][0]).path == "/polymarket/stocks/v1/stock/BK/mentions"


def test_polymarket_compare_preserves_graph_keys_and_nullable_metrics(api_server, tmp_path):
    base_url, state = api_server
    row = {"ticker": "BK", "buzz_score": None, "trade_count": 0, "market_count": 0,
           "current_market_count": 0, "total_liquidity": 0.0, "trend_history": []}
    state["payload"] = {"period_days": 7, "stocks": [row]}
    result = run_cli(base_url, tmp_path, "compare", "BNY", "SAP.DE", "BK", "--platform", "polymarket-stocks")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["data"]["stocks"][0]["buzz_score"] is None
    assert "company_name" not in payload["data"]["stocks"][0]
    assert parse_qs(urlparse(state["paths"][0]).query)["tickers"] == ["BNY,SAP.DE,BK"]
