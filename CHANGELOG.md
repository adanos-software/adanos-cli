# Changelog

All notable changes to `adanos-cli` will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

## [1.28.0] - 2026-05-25

### Changed
- Synced CLI endpoint coverage with Adanos Market Sentiment API `1.39.0`.
- Removed `--from`, `--to`, and `--days` from search endpoint calls and the top-level `adanos search` command; search endpoints now accept only `--limit` and use API-managed recent summary windows.

## [1.27.2] - 2026-05-21

### Fixed
- Improved endpoint error handling so API validation payloads are returned as CLI errors instead of successful endpoint results.
- Added a clear usage error for combining `--days` with both `--from` and `--to`.
- Removed `Recommended` wording from `--from` / `--to` help text.

## [1.27.1] - 2026-05-21

### Fixed
- Fixed top-level `adanos search` so `--limit` is accepted and period arguments are forwarded consistently.

## [1.27.0] - 2026-05-21

### Added
- Synced CLI endpoint and report coverage with Adanos Market Sentiment API `1.37.0`.
- Added recommended `--from` / `--to` period options for period-capable commands and endpoint calls.

### Changed
- Updated `/stats` handling expectations for API `1.36.0` compact standardized stats payloads.
- Kept `--days` working as a legacy v1-compatible shorthand and raised the Python SDK dependency floor to `adanos>=2.3.0`.

## [1.26.0] - 2026-05-19

### Added
- Synced endpoint coverage with Adanos Market Sentiment API `1.34.0`.
- Added `root.health` endpoint coverage and `adanos health --platform root`.
- Added raw mention `--offset` support across Reddit Stocks, News Stocks, X/Twitter Stocks, Polymarket Stocks, and Reddit Crypto endpoint calls.
- Documented Polymarket `current_market_count` as live active-market breadth.

### Changed
- Raised the Python SDK dependency floor to `adanos>=2.2.0` so CLI raw mention offset calls are supported by the installed SDK.

## [1.25.0] - 2026-04-29

### Added
- Added CLI endpoint coverage for raw mentions across Reddit Stocks, News Stocks, Reddit Crypto, X/Twitter Stocks, and Polymarket Stocks.
- Added `--include-inherited` for Reddit raw mention endpoint calls.
- Added `--dimension stocks` as an alias for main stock trending lists.

## [1.24.0] - 2026-04-20

### Changed
- Updated reports and screeners for API `1.25.0` canonical fields, using `mentions`, `sentiment_score`, and `total_upvotes` instead of removed response aliases.
- Relaxed the Python SDK dependency to allow the `adanos` 2.x release line.

## [1.23.0] - 2026-04-12

### Added
- Added `x-stocks.stock.explain` endpoint coverage and X/Twitter explanation context in stock/explain reports.

## [1.22.0] - 2026-03-27

### Added
- Added `market-sentiment` endpoint coverage across Reddit Stocks, News Stocks, Reddit Crypto, X/Twitter Stocks, and Polymarket Stocks in `adanos endpoint list` and `adanos endpoint call`.

### Changed
- Renamed CLI metadata and header text from `Adanos Finance Sentiment CLI` to `Adanos Market Sentiment CLI`.

## [1.21.0] - 2026-03-19

### Added
- Search commands now support `days` and `limit` across Reddit, News, X, Crypto, and Polymarket.

### Changed
- CLI endpoint output now matches the live API search `summary` contract and the enriched compare responses.
- CLI reports now prefer canonical `mentions` while still accepting the legacy `total_mentions` alias from the API.
- Published CLI builds now depend on the standalone `adanos` Python SDK, with a runtime fallback for older environments still using `stocksentiment`.

## [1.20.5] - 2026-03-17

### Changed
- Updated CLI onboarding to the live email-first auth flow: `register` now waits for verification instructions by email, and `redeem` now uses the new secure token redemption endpoint.

## [1.20.4] - 2026-03-17

### Added
- Added `adanos onboard recover --email ...` so existing users can trigger the secure email-based recovery flow from the CLI without exposing recovery tokens in terminal output.

## [1.20.3] - 2026-03-16

### Fixed
- Standalone release binaries now boot through a package-safe PyInstaller entry point instead of failing on relative imports.
- Shell installer checksum verification now accepts the `release-upload/` paths emitted by the binary release workflow.

## [1.20.2] - 2026-03-15

### Changed
- PyPI package metadata now points `Homepage` to `https://adanos.org` while keeping API documentation under `https://api.adanos.org/docs`.
- Release binary automation now uses supported GitHub macOS runners for both Intel and Apple Silicon builds.
- Homebrew formula output is now attached directly to each published GitHub Release alongside the binary archives.

## [1.20.1] - 2026-03-15

### Changed
- PyPI publishing now triggers only from a published GitHub Release in `adanos-software/adanos-cli`.
- Binary release automation now attaches artifacts to the published GitHub Release that owns the version tag.
- Package metadata now links directly to the public repository, releases page, PyPI project, and API docs.
- Public README was trimmed to user-facing install and usage guidance, keeping release operations out of the public surface.

## [1.20.0] - 2026-03-15

### Added
- First public standalone `adanos-cli` repository under `adanos-software/adanos-cli`.
- Public README focused on install, auth, trader workflows, and agent-friendly JSON usage.
- Standalone GitHub Actions CI for tests, build, and wheel smoke installation.
- Standalone binary release workflow for macOS and Linux, plus Homebrew formula generation.
- Standalone Trusted Publishing workflow for `adanos-cli` on PyPI from this repository.

### Changed
- CLI packaging now builds from the repository-local `src/` layout instead of monorepo-specific paths.
- Binary build tooling now reads the CLI package version directly from the package itself.
- CLI runtime no longer falls back to monorepo-local SDK imports when the published Python SDK is missing.
- PyPI release ownership moved out of the API monorepo and into `adanos-software/adanos-cli`.
