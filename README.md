# SessionsGen — Telegram String Session Bot

An owner-only Telegram bot for generating **Pyrogram** and **Telethon** user StringSessions for accounts you own.

## Features

- Telegram inline buttons for Pyrogram and Telethon.
- Phone, login-code and optional 2FA steps inside the private bot chat.
- Generated session is sent by the logged-in user client to that account's **Saved Messages** in monospace format.
- Bot chat receives only a completion notice; it does not send the session string there.
- Owner-ID allowlist; other Telegram users cannot start a generation flow.
- No database and no session files. Temporary login state is held in process memory only.
- Login input messages and bot prompts are deleted on a best-effort basis after processing.
- `/cancel` clears the active flow and disconnects the temporary client.

## Security

A StringSession is a full account credential. Anyone who obtains it may access the Telegram account. This bot is deliberately restricted to one configured `OWNER_ID`; do not make it public or add untrusted users.

The phone number, login code and optional 2FA password are sent through Telegram to your own bot and handled in RAM by your VPS. Input-message deletion is best-effort and is not a guarantee that Telegram or a device has no retained copy. Use only accounts you own, keep the VPS private, protect the bot token and API hash, and never enable request/body logging. The application does not write these values to a database or application log.

## Setup (Ubuntu 24.04 / Python 3.10+)

```bash
git clone https://github.com/OfficialBika/SessionsGen.git
cd SessionsGen
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Set these values in `.env`:

- `API_ID`, `API_HASH`: from https://my.telegram.org
- `BOT_TOKEN`: from @BotFather
- `OWNER_ID`: your numeric Telegram user ID

Start the bot:

```bash
python bot.py
```

Open your bot in Telegram using the configured owner account and send `/start` or `/generate`.

## Commands

- `/start` — open the menu
- `/generate` — choose Pyrogram or Telethon
- `/cancel` — cancel and clear the current temporary flow

## Notes

- The bot uses in-memory FSM storage; restarting the process clears the flow.
- The session is sent only to the authenticated Telegram account's Saved Messages.
- The session is not shown in the bot chat.
- Deleting chat messages is best-effort. Do not treat deletion as secure credential erasure.
