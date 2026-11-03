"""Local-only Pyrogram and Telethon session generator.

Login credentials are entered through the client library in the local terminal.
No bot endpoint receives OTPs, passwords, or session strings.
"""
from __future__ import annotations

import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"].strip()
except (KeyError, ValueError) as exc:
    raise SystemExit("Set valid API_ID and API_HASH in .env first.") from exc

if not API_HASH or API_HASH == "replace_with_your_api_hash":
    raise SystemExit("Set your real API_HASH in .env first.")


def choose_engine() -> str:
    print("\nSessionsGen — Local Session Tool")
    print("[1] Pyrogram")
    print("[2] Telethon")
    selected = input("Choose engine (1/2): ").strip()
    if selected not in {"1", "2"}:
        raise SystemExit("Invalid engine selection.")
    return selected


async def run_pyrogram() -> None:
    from pyrogram import Client
    from pyrogram.session import StringSession

    phone = input("Phone number (international format): ").strip()
    if not phone:
        raise SystemExit("Phone number is required.")

    # Pyrogram's interactive sign-in prompts run in this local terminal.
    client = Client(
        name="sessionsgen_ephemeral",
        api_id=API_ID,
        api_hash=API_HASH,
        in_memory=True,
        session_string=None,
    )

    session_string = None
    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        code = getpass("Telegram login code (hidden): ").strip()
        try:
            await client.sign_in(phone, sent_code.phone_code_hash, code)
        except Exception as exc:
            # 2FA is handled locally; never print or persist the password.
            from pyrogram.errors import SessionPasswordNeeded

            if not isinstance(exc, SessionPasswordNeeded):
                raise
            password = getpass("Telegram 2FA password (hidden): ")
            await client.check_password(password)
            del password

        session_string = await client.export_session_string()
        await client.send_message("me", f"<code>{session_string}</code>", parse_mode="html")
        print("Session sent to this account's Saved Messages.")
    finally:
        session_string = None
        try:
            await client.disconnect()
        except Exception:
            pass


async def run_telethon() -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    phone = input("Phone number (international format): ").strip()
    if not phone:
        raise SystemExit("Phone number is required.")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    session_string = None
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = getpass("Telegram login code (hidden): ").strip()
            try:
                await client.sign_in(phone=phone, code=code)
            except Exception as exc:
                from telethon.errors import SessionPasswordNeededError

                if not isinstance(exc, SessionPasswordNeededError):
                    raise
                password = getpass("Telegram 2FA password (hidden): ")
                await client.sign_in(password=password)
                del password

        session_string = client.session.save()
        # Saved Messages belongs to the authenticated account ('me').
        await client.send_message("me", f"<code>{session_string}</code>", parse_mode="html")
        print("Session sent to this account's Saved Messages.")
    finally:
        session_string = None
        await client.disconnect()


def main() -> None:
    choice = choose_engine()
    try:
        if choice == "1":
            asyncio.run(run_pyrogram())
        else:
            asyncio.run(run_telethon())
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception as exc:
        # Avoid logging credential-bearing objects or exception locals.
        print(f"Operation failed: {type(exc).__name__}. Check your local configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
