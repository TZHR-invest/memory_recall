#!/usr/bin/env python3
"""
Memory Recall Plugin Installation Script

Interactive setup that:
1. Asks for user_name and plugin_name
2. Checks if API keys exist
3. If no keys: auto-register
4. If keys exist: ask for existing API key
"""

import asyncio
import getpass
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.database import db
from src.api.auth import AuthService

CONFIG_FILE_PATH = Path.home() / ".config" / "opencode" / "memory-recall.jsonc"


async def check_existing_keys() -> bool:
    """Check if any API keys exist."""
    await db.connect()
    try:
        rows = await db.fetch("SELECT id FROM api_keys WHERE is_active = TRUE LIMIT 1")
        return len(rows) > 0
    finally:
        await db.disconnect()


async def register_new_key(user_name: str, plugin_name: str) -> dict:
    """Register a new API key."""
    auth_service = AuthService()

    result = await auth_service.create_key(
        user_id=user_name.lower().replace(" ", "-"),
        user_name=user_name,
        name=plugin_name,
        permissions=["read", "write", "delete", "admin"],
        is_test=False,
    )

    return {
        "api_key": result.key,
        "key_id": result.id,
        "user_name": user_name,
        "container_tag": result.id,
    }


async def validate_api_key(api_key: str) -> dict | None:
    """Validate an existing API key."""
    auth_service = AuthService()
    key_info = await auth_service.validate_key(api_key)

    if not key_info:
        return None

    return {
        "api_key": api_key,
        "key_id": str(key_info.id),
        "user_name": key_info.user_name or key_info.user_id,
        "container_tag": str(key_info.id),
    }


def save_config(api_key: str, user_name: str, base_url: str = "http://localhost:8000"):
    """Save configuration to file."""
    config_dir = CONFIG_FILE_PATH.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    config_data = {
        "apiKey": api_key,
        "baseUrl": base_url,
        "userName": user_name,
        "similarityThreshold": 0.6,
        "maxMemories": 5,
        "maxProjectMemories": 10,
        "injectProfile": True,
        "compactionThreshold": 0.8,
        "enableSummaryCapture": True,
        "enableDocumentTracking": True,
        "trackedDocPatterns": [
            "README*.md",
            "CHANGELOG*.md",
            "docs/**/*.md",
            "AGENTS.md",
        ],
        "language": "auto",
        "logLevel": "info",
    }

    CONFIG_FILE_PATH.write_text(json.dumps(config_data, indent=4))
    return CONFIG_FILE_PATH


def print_banner():
    print("\n" + "=" * 60)
    print("  Memory Recall Plugin Setup")
    print("=" * 60)
    print()


async def main():
    print_banner()

    # Step 1: Ask for API base URL
    print("Step 1: API Server")
    print("-" * 40)

    default_url = "http://localhost:8000"
    base_url = input(f"API server URL [{default_url}]: ").strip()
    if not base_url:
        base_url = default_url

    # Step 2: Ask for user name
    print()
    print("Step 2: User Information")
    print("-" * 40)

    default_user = (
        os.environ.get("USER") or os.environ.get("USERNAME") or getpass.getuser()
    )
    user_name = input(f"Your name [{default_user}]: ").strip()
    if not user_name:
        user_name = default_user

    # Step 3: Ask for plugin/key name
    print()
    print("Step 3: Plugin Name")
    print("-" * 40)
    print("This helps you identify this API key later.")

    default_plugin = "opencode-plugin"
    plugin_name = input(f"Plugin/key name [{default_plugin}]: ").strip()
    if not plugin_name:
        plugin_name = default_plugin

    # Step 4: Check existing keys
    print()
    print("Step 4: API Key Setup")
    print("-" * 40)

    has_existing_keys = await check_existing_keys()

    if has_existing_keys:
        print("Existing API keys found.")
        print()
        print("Options:")
        print("  1. Enter an existing API key")
        print("  2. Create a new API key (requires admin key)")
        print()

        choice = input("Choice [1]: ").strip() or "1"

        if choice == "1":
            print()
            api_key = input("Enter your API key (rk_live_xxx): ").strip()

            if not api_key.startswith("rk_"):
                print(
                    "\n❌ Invalid API key format. Must start with 'rk_live_' or 'rk_test_'"
                )
                sys.exit(1)

            print("\nValidating API key...")
            result = await validate_api_key(api_key)

            if not result:
                print("❌ Invalid or expired API key")
                sys.exit(1)

            print(f"✓ API key validated")
            print(f"  User: {result['user_name']}")
            print(f"  Container: {result['container_tag']}")

        else:
            print("\n⚠ Creating new key requires admin authentication.")
            print("Please use: curl -X POST http://localhost:8000/auth/api-keys ...")
            sys.exit(1)
    else:
        print("No existing API keys found. Creating new one...")

        result = await register_new_key(user_name, plugin_name)

        print()
        print("✓ API key created!")
        print(f"  User: {result['user_name']}")
        print(f"  Key ID: {result['key_id']}")
        print(f"  Container: {result['container_tag']}")
        print()
        print("  ⚠️  Save this API key (shown only once):")
        print(f"  {result['api_key']}")

    # Step 5: Save config
    print()
    print("Step 5: Save Configuration")
    print("-" * 40)

    config_path = save_config(result["api_key"], result["user_name"], base_url)

    print(f"✓ Configuration saved to:")
    print(f"  {config_path}")

    # Step 6: Summary
    print()
    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print("Configuration:")
    print(f"  API Server:   {base_url}")
    print(f"  User Name:    {result['user_name']}")
    print(f"  API Key:      {result['api_key'][:20]}...")
    print(f"  Container:    {result['container_tag']}")
    print()
    print("Next steps:")
    print("  1. Restart OpenCode to load the plugin")
    print("  2. Use 'memory-recall' tool to store/retrieve memories")
    print()


if __name__ == "__main__":
    asyncio.run(main())
