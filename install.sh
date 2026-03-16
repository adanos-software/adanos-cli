#!/usr/bin/env bash
set -euo pipefail

REPO="adanos-software/adanos-cli"
LATEST_BASE_URL="https://github.com/${REPO}/releases/latest/download"
DEFAULT_INSTALL_DIR="${HOME}/.local/bin"
INSTALL_DIR="${ADANOS_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

detect_asset() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"

  case "$os" in
    Darwin)
      case "$arch" in
        arm64|aarch64) printf 'adanos-darwin-arm64.tar.gz' ;;
        x86_64|amd64) printf 'adanos-darwin-x86_64.tar.gz' ;;
        *) fail "unsupported macOS architecture: ${arch}" ;;
      esac
      ;;
    Linux)
      case "$arch" in
        x86_64|amd64) printf 'adanos-linux-x86_64.tar.gz' ;;
        *) fail "unsupported Linux architecture: ${arch}" ;;
      esac
      ;;
    *)
      fail "unsupported operating system: ${os}"
      ;;
  esac
}

verify_checksum() {
  local archive_path checksums_path asset_name expected actual
  archive_path="$1"
  checksums_path="$2"
  asset_name="$3"

  expected="$(awk -v asset="$asset_name" '$2 ~ ("(^|/)" asset "$") {print $1; exit}' "$checksums_path")"
  [ -n "$expected" ] || fail "could not find checksum for ${asset_name}"

  if command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
  elif command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$archive_path" | awk '{print $1}')"
  else
    fail "missing checksum tool (shasum or sha256sum)"
  fi

  [ "$actual" = "$expected" ] || fail "checksum mismatch for ${asset_name}"
}

print_path_hint() {
  case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) ;;
    *)
      log
      log "Add this to your shell profile if needed:"
      log "  export PATH=\"${INSTALL_DIR}:\$PATH\""
      ;;
  esac
}

main() {
  require_cmd curl
  require_cmd tar
  require_cmd mktemp
  require_cmd install

  local asset_name tmp_dir archive_path checksums_path
  asset_name="$(detect_asset)"
  tmp_dir="$(mktemp -d)"
  archive_path="${tmp_dir}/${asset_name}"
  checksums_path="${tmp_dir}/SHA256SUMS.txt"

  log "Downloading ${asset_name}..."
  curl -fsSL "${LATEST_BASE_URL}/${asset_name}" -o "$archive_path"
  curl -fsSL "${LATEST_BASE_URL}/SHA256SUMS.txt" -o "$checksums_path"

  verify_checksum "$archive_path" "$checksums_path" "$asset_name"

  mkdir -p "${INSTALL_DIR}"
  tar -xzf "$archive_path" -C "$tmp_dir"
  install -m 0755 "${tmp_dir}/adanos" "${INSTALL_DIR}/adanos"

  rm -rf "$tmp_dir"

  log
  log "Installed adanos to ${INSTALL_DIR}/adanos"
  print_path_hint
  log
  log "Verify with:"
  log "  adanos --version"
}

main "$@"
