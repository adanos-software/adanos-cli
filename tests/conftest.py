from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

for path in (REPO_ROOT, SRC_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch) -> None:
    import adanos_cli.config as cli_config

    cfg_dir = tmp_path / ".config" / "adanos-cli"
    monkeypatch.setattr(cli_config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", cfg_dir / "config.json")
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", cfg_dir / "credentials.json")
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    monkeypatch.setenv("ADANOS_CLI_DISABLE_UPDATE_CHECK", "1")
