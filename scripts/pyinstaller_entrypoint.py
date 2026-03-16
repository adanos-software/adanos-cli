#!/usr/bin/env python3
"""PyInstaller entry point for the standalone adanos binary."""

from adanos_cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
