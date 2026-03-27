#!/usr/bin/env python3
"""Generate a Homebrew formula for prebuilt adanos CLI binaries."""

from __future__ import annotations

import argparse
from pathlib import Path


def render_formula(
    *,
    version: str,
    darwin_arm64_url: str,
    darwin_arm64_sha256: str,
    darwin_x86_64_url: str,
    darwin_x86_64_sha256: str,
    linux_x86_64_url: str,
    linux_x86_64_sha256: str,
) -> str:
    return f"""class AdanosCli < Formula
  desc "Comprehensive CLI for the Adanos Market Sentiment API"
  homepage "https://adanos.org"
  version "{version}"

  on_macos do
    if Hardware::CPU.arm?
      url "{darwin_arm64_url}"
      sha256 "{darwin_arm64_sha256}"
    else
      url "{darwin_x86_64_url}"
      sha256 "{darwin_x86_64_sha256}"
    end
  end

  on_linux do
    url "{linux_x86_64_url}"
    sha256 "{linux_x86_64_sha256}"
  end

  def install
    bin.install "adanos"
  end

  test do
    assert_match "adanos", shell_output("#{{bin}}/adanos --help")
  end
end
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Homebrew formula for adanos-cli.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--darwin-arm64-url", required=True)
    parser.add_argument("--darwin-arm64-sha256", required=True)
    parser.add_argument("--darwin-x86_64-url", required=True)
    parser.add_argument("--darwin-x86_64-sha256", required=True)
    parser.add_argument("--linux-x86_64-url", required=True)
    parser.add_argument("--linux-x86_64-sha256", required=True)
    parser.add_argument("--output", help="Optional path to write the formula")
    args = parser.parse_args()

    formula = render_formula(
        version=args.version,
        darwin_arm64_url=args.darwin_arm64_url,
        darwin_arm64_sha256=args.darwin_arm64_sha256,
        darwin_x86_64_url=args.darwin_x86_64_url,
        darwin_x86_64_sha256=args.darwin_x86_64_sha256,
        linux_x86_64_url=args.linux_x86_64_url,
        linux_x86_64_sha256=args.linux_x86_64_sha256,
    )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(formula, encoding="utf-8")
    else:
        print(formula, end="")


if __name__ == "__main__":
    main()
