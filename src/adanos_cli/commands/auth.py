"""Auth profile command handlers."""

from __future__ import annotations

from getpass import getpass
from argparse import Namespace

from .. import config as cli_config
from ..config import DEFAULT_BASE_URL, load_config_file, masked_key, save_config_file
from ..utils import CliUsageError, print_json, with_json_metadata
from ..tty import is_interactive


def _prompt_api_key() -> str:
    value = getpass("API key: ").strip()
    if not value:
        raise CliUsageError("API key must not be empty.")
    return value


def handle_auth_command(args: Namespace) -> int:
    if args._handler == "auth_login":
        profile_name = getattr(args, "profile", None)
        if profile_name:
            validation_error = cli_config.validate_profile_name(profile_name)
            if validation_error:
                raise CliUsageError(validation_error)
        api_key = str(getattr(args, "api_key", "") or "").strip()
        if not api_key:
            if not is_interactive():
                raise CliUsageError("Non-interactive usage requires --api-key.")
            api_key = _prompt_api_key()
        save_config_file(
            api_key=api_key,
            base_url=args.base_url,
            profile_name=profile_name,
        )
        target_profile = profile_name or cli_config.get_active_profile_name()
        payload = {
            "ok": True,
            "action": "auth_login",
            "profile": target_profile,
            "config_path": str(cli_config.CONFIG_PATH),
            "credentials_path": str(cli_config.CREDENTIALS_PATH),
        }
        if args.json:
            print_json(with_json_metadata(payload, kind="auth_login", command="auth", subcommand="login"))
        else:
            print(f'Logged in profile "{target_profile}".')
            print(f"Credentials saved: {cli_config.CREDENTIALS_PATH}")
            print(f"Config saved: {cli_config.CONFIG_PATH}")
        return 0

    if args._handler == "auth_logout":
        removed_profile = cli_config.delete_profile(getattr(args, "profile", None))
        payload = {
            "ok": True,
            "action": "auth_logout",
            "profile": removed_profile,
            "credentials_path": str(cli_config.CREDENTIALS_PATH),
        }
        if args.json:
            print_json(with_json_metadata(payload, kind="auth_logout", command="auth", subcommand="logout"))
        else:
            print(f'Removed profile "{removed_profile}".')
        return 0

    if args._handler == "auth_list":
        profiles = [
            {
                "name": item["name"],
                "active": item["active"],
                "api_key": masked_key(item["api_key"]),
            }
            for item in cli_config.list_profiles()
        ]
        payload = {
            "ok": True,
            "action": "auth_list",
            "active_profile": cli_config.get_active_profile_name() if profiles else None,
            "profiles": profiles,
        }
        if args.json:
            print_json(with_json_metadata(payload, kind="auth_profile_list", command="auth", subcommand="list"))
        else:
            if not profiles:
                print("No local auth profiles configured.")
            for item in profiles:
                marker = "*" if item["active"] else "-"
                print(f"{marker} {item['name']}: {item['api_key']}")
        return 0

    if args._handler == "auth_switch":
        cli_config.set_active_profile(args.profile)
        payload = {
            "ok": True,
            "action": "auth_switch",
            "profile": args.profile,
            "credentials_path": str(cli_config.CREDENTIALS_PATH),
        }
        if args.json:
            print_json(with_json_metadata(payload, kind="auth_switch", command="auth", subcommand="switch"))
        else:
            print(f'Active profile: "{args.profile}"')
        return 0

    if args._handler == "auth_current":
        active_profile = cli_config.get_active_profile_name()
        current_profile = cli_config.get_profile(active_profile)
        payload = {
            "ok": True,
            "action": "auth_current",
            "profile": active_profile if current_profile else None,
            "api_key": masked_key(str((current_profile or {}).get("api_key") or "")),
            "credentials_path": str(cli_config.CREDENTIALS_PATH),
            "base_url": load_config_file().get("base_url") or DEFAULT_BASE_URL,
        }
        if args.json:
            print_json(with_json_metadata(payload, kind="auth_profile", command="auth", subcommand="current"))
        else:
            if payload["profile"] is None:
                print("No active auth profile configured.")
            else:
                print(f"Active profile: {payload['profile']}")
                print(f"API key: {payload['api_key']}")
                print(f"Base URL: {payload['base_url']}")
        return 0

    raise CliUsageError("Unknown auth command")
