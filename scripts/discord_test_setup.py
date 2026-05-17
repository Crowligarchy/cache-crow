#!/usr/bin/env python3
"""
scripts/discord_test_setup.py — Discord two-account test infrastructure setup.

Sets up (or verifies) the Discord test environment for cache-crow integration
testing. Run once to provision resources; subsequent runs detect existing state
and skip redundant API calls.

Usage:
    source ~/.crowligarchy/credentials.env
    python scripts/discord_test_setup.py

What it does:
    1. Verifies both Discord accounts (A and B) are reachable via their tokens.
    2. Uses Account B (cachecrow_beta) to create the 'cache-crow-test' guild
       if not already created (Account A is blocked by verification requirement).
    3. Creates a #test-media text channel in the guild if not present.
    4. Creates an invite link for Account A to join (even if A can't currently
       use it due to verification requirements; documents the intended flow).
    5. Sends a test text message from Account B to verify channel access.
    6. Sends a test PNG attachment from Account B and captures CDN URL.
    7. Verifies CDN URL resolves.
    8. Prints a summary with all IDs for use in credentials.env.

Account notes:
    Account A (cachecrow_alpha, id=1505495625385640027):
        - Token: DISCORD_ACCOUNT_A_TOKEN
        - Status: Unverified — cannot create guilds, join via invite, or open DMs
        - Role in tests: intended sender; currently blocked by Discord anti-abuse
          verification. All sender actions performed by Account B as workaround.

    Account B (cachecrow_beta, id=1505496469640183858):
        - Token: DISCORD_TOKEN_B
        - Status: Fully functional
        - Role in tests: guild owner, sender, channel reader

Environment variables required:
    DISCORD_ACCOUNT_A_TOKEN
    DISCORD_TOKEN_B
    DISCORD_TEST_GUILD_ID   (optional — script creates guild if not set)
    DISCORD_TEST_CHANNEL_ID (optional — script creates channel if not set)
"""

from __future__ import annotations

import io
import json
import os
import struct
import sys
import time
import zlib

import requests

BASE = "https://discord.com/api/v10"

SUPER_PROPS = (
    "eyJvcyI6IkxpbnV4IiwiYnJvd3NlciI6IkRpc2NvcmQiLCJyZWxlYXNlX2NoYW5uZWwiOiJzdGFibGUiL"
    "CJjbGllbnRfdmVyc2lvbiI6IjAuMC41OSIsIm9zX3ZlcnNpb24iOiI2LjEuMCIsIm9zX2FyY2giOiJ4NjQi"
    "LCJhcHBfYXJjaCI6Ing2NCIsInN5c3RlbV9sb2NhbGUiOiJlbi1VUyIsImJyb3dzZXJfdXNlcl9hZ2VudCI"
    "6Ik1vemlsbGEvNS4wIChYMTE7IExpbnV4IHg4Nl82NCkgQXBwbGVXZWJLaXQvNTM3LjM2IiwiYnJvd3Nlcl"
    "92ZXJzaW9uIjoiMTIwLjAuMC4wIiwiY2xpZW50X2J1aWxkX251bWJlciI6MjcwNTkzLCJuYXRpdmVfYnVpb"
    "GRfbnVtYmVyIjpudWxsLCJjbGllbnRFdmVudFNvdXJjZSI6bnVsbH0="
)


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "X-Discord-Locale": "en-US",
        "X-Super-Properties": SUPER_PROPS,
    }


def make_red_png(width: int = 50, height: int = 50) -> bytes:
    """Generate a minimal valid 50x50 solid-red PNG."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        payload = tag + data
        crc = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        return length + payload + crc

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b"".join(b"\x00" + b"\xFF\x00\x00" * width for _ in range(height))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def ok(text: str) -> None:
    print(f"  [OK] {text}")


def info(text: str) -> None:
    print(f"  [--] {text}")


def warn(text: str) -> None:
    print(f"  [!!] {text}", file=sys.stderr)


def err(text: str) -> None:
    print(f"  [ERROR] {text}", file=sys.stderr)


def get_env(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        err(f"Environment variable {key} is not set.")
        err("Run: source ~/.crowligarchy/credentials.env")
        sys.exit(1)
    return val


def verify_account(token: str, label: str) -> dict:
    print(f"\n[{label}] Verifying account...")
    resp = requests.get(f"{BASE}/users/@me", headers=headers(token), timeout=10)
    if resp.status_code != 200:
        err(f"Account verification failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    user = resp.json()
    ok(f"Username: {user['username']} (id={user['id']})")
    ok(f"Email verified: {user.get('verified')}")
    return user


def create_guild_if_needed(token_b: str, existing_guild_id: str | None) -> tuple[str, str]:
    """
    Returns (guild_id, channel_id).
    Uses token_b (Account B) since Account A is unverified.
    """
    if existing_guild_id:
        print(f"\n[Guild] Using existing guild: {existing_guild_id}")
        resp = requests.get(
            f"{BASE}/guilds/{existing_guild_id}/channels",
            headers=headers(token_b),
            timeout=10,
        )
        if resp.status_code == 200:
            channels = resp.json()
            for ch in channels:
                if ch["name"] == "test-media" and ch["type"] == 0:
                    ok(f"Found #test-media channel: {ch['id']}")
                    return existing_guild_id, ch["id"]
        warn("Could not find #test-media channel in existing guild — creating new guild.")

    print("\n[Guild] Creating 'cache-crow-test' guild with Account B...")
    resp = requests.post(
        f"{BASE}/guilds",
        headers=headers(token_b),
        json={"name": "cache-crow-test", "channels": [{"name": "test-media", "type": 0}]},
        timeout=15,
    )
    if resp.status_code != 200:
        err(f"Guild creation failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    guild = resp.json()
    guild_id = guild["id"]
    ok(f"Guild created: {guild['name']} (id={guild_id})")

    # Get channel ID
    resp2 = requests.get(
        f"{BASE}/guilds/{guild_id}/channels",
        headers=headers(token_b),
        timeout=10,
    )
    channels = resp2.json()
    channel_id = None
    for ch in channels:
        if ch["name"] == "test-media" and ch["type"] == 0:
            channel_id = ch["id"]
            break
    if not channel_id:
        err("Could not find #test-media channel after guild creation.")
        sys.exit(1)
    ok(f"Channel #test-media: {channel_id}")
    return guild_id, channel_id


def create_invite(token_b: str, channel_id: str) -> str:
    print("\n[Invite] Creating invite link...")
    resp = requests.post(
        f"{BASE}/channels/{channel_id}/invites",
        headers=headers(token_b),
        json={"max_age": 0, "max_uses": 10},
        timeout=10,
    )
    if resp.status_code != 200:
        err(f"Invite creation failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    code = resp.json()["code"]
    ok(f"Invite code: {code} (discord.gg/{code})")
    return code


def attempt_account_a_join(token_a: str, invite_code: str) -> None:
    print("\n[Account A] Attempting to join guild via invite...")
    resp = requests.post(
        f"{BASE}/invites/{invite_code}",
        headers=headers(token_a),
        json={},
        timeout=10,
    )
    if resp.status_code == 200:
        ok("Account A joined successfully!")
    else:
        data = resp.json()
        code = data.get("code", "?")
        msg = data.get("message", "?")
        warn(f"Account A join failed ({resp.status_code}): [{code}] {msg}")
        if code == 40002:
            info(
                "Known issue: Account A (cachecrow_alpha) requires Discord email/phone "
                "verification. This is a Discord anti-abuse restriction on new accounts. "
                "Account B (cachecrow_beta) serves as sender in integration tests."
            )


def send_test_message(token_b: str, channel_id: str) -> str:
    print("\n[Messages] Sending text message from Account B...")
    resp = requests.post(
        f"{BASE}/channels/{channel_id}/messages",
        headers=headers(token_b),
        json={"content": "cache-crow setup verification message from cachecrow_beta"},
        timeout=10,
    )
    if resp.status_code != 200:
        err(f"Message send failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    msg_id = resp.json()["id"]
    ok(f"Message sent: {msg_id}")
    return msg_id


def send_png_attachment(token_b: str, channel_id: str) -> tuple[str, str]:
    """Returns (message_id, cdn_url)."""
    print("\n[Attachment] Sending test PNG attachment from Account B...")
    png_bytes = make_red_png()
    h = headers(token_b)
    h.pop("Content-Type", None)  # Let requests set multipart Content-Type

    resp = requests.post(
        f"{BASE}/channels/{channel_id}/messages",
        headers=h,
        data={"payload_json": json.dumps({"content": "cache-crow attachment test (50x50 red PNG)"})},
        files={"files[0]": ("test_red.png", io.BytesIO(png_bytes), "image/png")},
        timeout=15,
    )
    if resp.status_code != 200:
        err(f"Attachment send failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    attachments = data.get("attachments", [])
    if not attachments:
        err("Message sent but no attachments in response.")
        sys.exit(1)

    cdn_url = attachments[0]["url"]
    message_id = data["id"]
    ok(f"Attachment message: {message_id}")
    ok(f"CDN URL: {cdn_url[:80]}...")
    ok(f"Dimensions: {attachments[0].get('width')}x{attachments[0].get('height')}")
    return message_id, cdn_url


def verify_cdn_url(cdn_url: str) -> None:
    print("\n[CDN] Verifying CDN URL resolves...")
    resp = requests.get(cdn_url, timeout=15)
    if resp.status_code == 200 and resp.content[:4] == b"\x89PNG":
        ok(f"CDN resolves: {resp.status_code}, {len(resp.content)} bytes, valid PNG")
    else:
        warn(f"CDN returned {resp.status_code} — {resp.text[:100]}")


def verify_channel_history(token_b: str, channel_id: str) -> None:
    print("\n[History] Verifying Account B can read channel history...")
    resp = requests.get(
        f"{BASE}/channels/{channel_id}/messages",
        headers=headers(token_b),
        timeout=10,
    )
    if resp.status_code != 200:
        err(f"Channel history read failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    messages = resp.json()
    ok(f"Channel history: {len(messages)} message(s) visible")
    for m in messages[:3]:
        ok(f"  [{m['id']}] {m['author']['username']}: {m['content'][:60]}")


def main() -> None:
    print("=" * 60)
    print("cache-crow Discord Test Infrastructure Setup")
    print("=" * 60)

    # Load tokens
    token_a = get_env("DISCORD_ACCOUNT_A_TOKEN")
    token_b = get_env("DISCORD_TOKEN_B")
    existing_guild_id = os.environ.get("DISCORD_TEST_GUILD_ID", "")
    existing_channel_id = os.environ.get("DISCORD_TEST_CHANNEL_ID", "")

    # Verify both accounts
    user_a = verify_account(token_a, "Account A")
    user_b = verify_account(token_b, "Account B")

    # Create or verify guild
    guild_id, channel_id = create_guild_if_needed(token_b, existing_guild_id or None)

    # Create invite and attempt Account A join
    invite_code = create_invite(token_b, channel_id)
    attempt_account_a_join(token_a, invite_code)

    # Send messages
    send_test_message(token_b, channel_id)
    attachment_msg_id, cdn_url = send_png_attachment(token_b, channel_id)

    # Verify CDN and channel history
    verify_cdn_url(cdn_url)
    verify_channel_history(token_b, channel_id)

    # Print summary
    print("\n" + "=" * 60)
    print("SETUP COMPLETE — add to credentials.env if not already present:")
    print("=" * 60)
    print(f"DISCORD_TEST_GUILD_ID={guild_id}")
    print(f"DISCORD_TEST_CHANNEL_ID={channel_id}")
    print(f"DISCORD_TEST_INVITE={invite_code}")
    print()
    print("Account IDs:")
    print(f"  Account A (cachecrow_alpha): {user_a['id']}")
    print(f"  Account B (cachecrow_beta):  {user_b['id']}")
    print()
    print("Known restrictions:")
    print("  Account A: blocked by Discord verification (code 40002)")
    print("  Account B: fully functional — acts as sender in integration tests")
    print()
    print("Run integration tests:")
    print("  source ~/.crowligarchy/credentials.env")
    print("  pytest tests/test_integration.py -v -m integration")


if __name__ == "__main__":
    main()
