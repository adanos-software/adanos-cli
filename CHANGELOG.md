# Changelog

All notable changes to `adanos-cli` will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

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
