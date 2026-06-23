# adanos-cli

[![PyPI version](https://img.shields.io/pypi/v/adanos-cli.svg)](https://pypi.org/project/adanos-cli/)

`adanos-cli` is the command-line client for the [Adanos Market Sentiment API](https://api.adanos.org/docs).

It is built for three use cases:
- traders who want fast stock and crypto sentiment reports
- analysts who want repeatable CLI workflows
- agents and automation that need stable JSON output

The CLI is versioned independently from the API backend. It targets the public API at `https://api.adanos.org/docs` and uses the published Python SDK under the hood.

## Install

### Recommended

```bash
pipx install adanos-cli
```

### cURL

```bash
curl -fsSL https://raw.githubusercontent.com/adanos-software/adanos-cli/main/install.sh | bash
```

The shell installer downloads the latest standalone binary for:
- macOS arm64
- macOS x86_64
- Linux x86_64

By default it installs to `~/.local/bin`. Override with `ADANOS_INSTALL_DIR=/your/path`.

### Homebrew (macOS / Linux)

```bash
brew install adanos-software/tap/adanos-cli
```

### PowerShell (Windows)

```powershell
irm https://raw.githubusercontent.com/adanos-software/adanos-cli/main/install.ps1 | iex
```

### Plain pip

```bash
python3 -m pip install adanos-cli
```

### From source

```bash
git clone https://github.com/adanos-software/adanos-cli.git
cd adanos-cli
python3 -m pip install -e ".[dev]"
```

## Quick Start

If you already have an API key:

```bash
adanos login --api-key sk_live_xxx
adanos whoami
adanos doctor
```

First market checks:

```bash
adanos consensus TSLA
adanos explain TSLA --profile investor
adanos scan --asset stocks --style daytrader --top 10
```

Crypto:

```bash
adanos crypto BTC
adanos crypto BTC/ETH
```

## Start Modes

`adanos` shows a compact start screen with the CLI header and next actions.

```bash
adanos
```

Explicit interactive shell:

```bash
adanos shell
```

One-shot command mode:

```bash
adanos stock NVDA
```

## Authentication

Persist a key locally:

```bash
adanos login --api-key sk_live_xxx
```

Request a recovery email for an existing account:

```bash
adanos onboard recover --email you@example.com
```

Start a new signup from the CLI:

```bash
adanos onboard register --name "Jane Doe" --email "jane@example.com" --purpose "Trading research"
# then redeem the one-time token from the verification email
adanos onboard redeem --token kt_xxx --save
```

Use profiles:

```bash
adanos auth login --api-key sk_live_prod --profile prod
adanos auth login --api-key sk_live_staging --profile staging
adanos auth switch prod
adanos auth current --json
```

Priority order:
- `--api-key`
- `ADANOS_API_KEY`
- stored credentials in the active profile

## Common Workflows

Stock report:

```bash
adanos stock TSLA
```

Cross-platform consensus:

```bash
adanos consensus TSLA
```

Narrative explanation:

```bash
adanos explain TSLA --profile investor
```

Watchlists:

```bash
adanos watchlist add core --asset stocks --symbols TSLA,NVDA,AAPL
adanos watchlist report core --asset stocks
adanos watch core --kind watchlist --asset stocks --refresh 60 --iterations 1
```

Raw endpoint access:

```bash
adanos endpoint list
adanos endpoint call root.health
adanos endpoint call reddit-stocks.trending --limit 10
adanos endpoint call reddit-stocks.market-sentiment --from 2026-05-01 --to 2026-05-07
adanos endpoint call reddit-stocks.stock.mentions --ticker TSLA --from 2026-05-01 --to 2026-05-07 --limit 10 --offset 10 --include-inherited
adanos endpoint call x-stocks.stock.explain --ticker TSLA
adanos endpoint call sentiment.analyze --text "TSLA looks like a short squeeze setup"
```

Polymarket endpoint output includes both `market_count` for selected-window breadth and `current_market_count` for live-only active-market breadth.

Period-capable commands and endpoint calls accept `--from YYYY-MM-DD` and `--to YYYY-MM-DD` as inclusive UTC date windows. `--days N` remains available for v1 compatibility, but is legacy; combining `--from`, `--to` and `--days` returns API validation error `422`. Search commands are the exception: they accept only `--limit` and use the API-managed recent summary window.

## AI / Automation

The CLI supports machine-readable output via `--output json` or `--quiet`.

```bash
adanos --quiet capabilities
adanos --quiet whoami
adanos --quiet doctor
adanos --quiet ask "How does TSLA look?"
adanos --quiet endpoint call news-stocks.trending --limit 3
```

JSON conventions:
- object payloads include a stable `kind`
- command wrappers include `command`, and `subcommand` when relevant
- endpoint-backed payloads include `platform`, `route`, `endpoint`, `path`, and `data`

## Diagnostics

Identity and runtime context:

```bash
adanos whoami
```

Problem-focused self-check:

```bash
adanos doctor
adanos doctor --verbose
```

## Releases

Tagged releases build standalone archives for:
- macOS arm64
- macOS x86_64
- Linux x86_64

The repo also generates a Homebrew formula artifact for each tagged binary release and can publish it to `adanos-software/homebrew-tap` when `HOMEBREW_TAP_TOKEN` is configured.

PyPI publishing also happens from this repo, not from the API monorepo.

## Development

Install the repo in editable mode:

```bash
python3 -m pip install -e ".[dev]"
```

Run tests:

```bash
python3 -m pytest tests -q
```

Build wheel and sdist:

```bash
python3 -m build
```

Build a standalone binary archive locally:

```bash
python3 scripts/build_cli_binary.py --output-dir dist-binaries
```

Generate a Homebrew formula:

```bash
VERSION=$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("src/adanos_cli/__init__.py").read_text(encoding="utf-8")
print(re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1))
PY
)

python3 scripts/generate_homebrew_formula.py \
  --version "$VERSION" \
  --darwin-arm64-url "https://example.com/adanos-cli-${VERSION}-darwin-arm64.tar.gz" \
  --darwin-arm64-sha256 <sha256> \
  --darwin-x86_64-url "https://example.com/adanos-cli-${VERSION}-darwin-x86_64.tar.gz" \
  --darwin-x86_64-sha256 <sha256> \
  --linux-x86_64-url "https://example.com/adanos-cli-${VERSION}-linux-x86_64.tar.gz" \
  --linux-x86_64-sha256 <sha256> \
  --output dist/homebrew/adanos-cli.rb
```

## License

MIT
