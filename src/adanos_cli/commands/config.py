"""Config command handlers."""

from __future__ import annotations

from argparse import Namespace

from .. import config as cli_config
from ..config import DEFAULT_BASE_URL, clear_config_file, load_config_file, masked_key, save_config_file
from ..utils import CliUsageError, print_json, with_json_metadata


def handle_config_command(args: Namespace) -> int:
    if args._handler == "config_set":
        save_config_file(
            api_key=args.api_key,
            base_url=args.base_url,
            profile_name=getattr(args, "profile", None),
        )
        if args.json:
            print_json(
                with_json_metadata(
                    {
                        "ok": True,
                        "action": "config_set",
                        "config_path": str(cli_config.CONFIG_PATH),
                        "credentials_path": str(cli_config.CREDENTIALS_PATH),
                    },
                    kind="config_set",
                    command="config",
                    subcommand="set",
                )
            )
        else:
            print(f"Config saved: {cli_config.CONFIG_PATH}")
            print(f"Credentials saved: {cli_config.CREDENTIALS_PATH}")
        return 0

    if args._handler == "config_show":
        cfg = load_config_file()
        active_profile = cli_config.get_active_profile_name()
        current_profile = cli_config.get_profile(active_profile)
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
            "action": "config_show",
            "config_path": str(cli_config.CONFIG_PATH),
            "credentials_path": str(cli_config.CREDENTIALS_PATH),
            "active_profile": active_profile if current_profile else None,
            "api_key": masked_key(str((current_profile or {}).get("api_key") or cfg.get("api_key") or "")),
            "base_url": cfg.get("base_url") or DEFAULT_BASE_URL,
            "profiles": profiles,
        }
        if args.json:
            print_json(with_json_metadata(payload, kind="config_show", command="config", subcommand="show"))
        else:
            print(f"Config file: {cli_config.CONFIG_PATH}")
            print(f"Credentials file: {cli_config.CREDENTIALS_PATH}")
            if payload["active_profile"]:
                print(f"Active profile: {payload['active_profile']}")
            print(f"API key: {payload['api_key']}")
            print(f"Base URL: {payload['base_url']}")
        return 0

    if args._handler == "config_clear":
        clear_config_file()
        if args.json:
            print_json(
                with_json_metadata(
                    {
                        "ok": True,
                        "action": "config_clear",
                        "config_path": str(cli_config.CONFIG_PATH),
                        "credentials_path": str(cli_config.CREDENTIALS_PATH),
                    },
                    kind="config_clear",
                    command="config",
                    subcommand="clear",
                )
            )
        else:
            print(f"Config removed: {cli_config.CONFIG_PATH}")
            print(f"Credentials removed: {cli_config.CREDENTIALS_PATH}")
        return 0

    raise CliUsageError("Unknown config command")
