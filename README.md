# SessionsGen

A **local-only** Telegram session utility for accounts you own.

## Engines

- **Pyrogram** — create a Pyrogram StringSession locally.
- **Telethon** — create a Telethon StringSession locally.

The Telegram login code and 2FA password are entered only in your local terminal through the client library's interactive prompts. They are never sent to a Telegram bot, administrator, web service, or GitHub.

## Requirements

- Python 3.10+
- Telegram API ID and API hash from https://my.telegram.org

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your own API credentials.

## Run

```bash
python -m local_session
```

Choose Pyrogram or Telethon. Complete login in the local terminal. The tool sends the generated session to the **currently logged-in account's Saved Messages** as a monospace message, then clears the in-memory reference. It does not write a session file or store sessions in a database or log.

## Important security notes

A StringSession is equivalent to an account credential. Anyone who obtains it may gain access to the Telegram account. Treat it like a password. Do not paste it into chats, issues, logs, screenshots, or source control. Use this utility only for accounts you own or are explicitly authorized to administer.

The project deliberately does not provide a bot endpoint that collects users' phone numbers, OTPs, 2FA passwords, or exports their session strings. A Telegram bot cannot securely prove account ownership merely because a user is allowed by an owner-ID check.

## Cleanup

The session is held only in process memory until it is sent. The application does not persist it. For extra protection, run this on a trusted device and keep disk encryption enabled.
