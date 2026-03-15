# Changelog

All notable changes to `adanos-cli` will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

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
