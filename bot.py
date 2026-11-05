from __future__ import annotations

import asyncio
import html
import logging
import os
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
OWNER_ID_RAW = os.getenv("OWNER_ID", "").strip()
try:
    API_ID = int(os.getenv("API_ID", ""))
    OWNER_ID = int(OWNER_ID_RAW)
except ValueError as exc:
    raise SystemExit("API_ID and OWNER_ID must be valid integers.") from exc

if not BOT_TOKEN or not API_HASH:
    raise SystemExit("BOT_TOKEN and API_HASH are required in .env.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("sessionsgen")

class GenerateFlow(StatesGroup):
    phone = State()
    code = State()
    password = State()

# Clients and prompt IDs live only in RAM. There is no database or session file.
ACTIVE: dict[int, dict[str, Any]] = {}
EXPIRY_TASKS: dict[int, asyncio.Task] = {}

def owner_only(user_id: int | None) -> bool:
    return user_id == OWNER_ID

def engine_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📘 Pyrogram", callback_data="engine:pyrogram"),
            InlineKeyboardButton(text="📗 Telethon", callback_data="engine:telethon"),
        ],
        [InlineKeyboardButton(text="✖ Cancel", callback_data="cancel")],
    ])

async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        # Telegram may reject deletion; never log the message body.
        pass

async def delete_prompts(bot: Bot, user_id: int, data: dict[str, Any]) -> None:
    for message_id in data.get("prompt_ids", []):
        try:
            await bot.delete_message(user_id, message_id)
        except TelegramBadRequest:
            pass
        except Exception:
            pass

async def disconnect_client(data: dict[str, Any]) -> None:
    client = data.get("client")
    if client is not None:
        try:
            await client.disconnect()
        except Exception:
            pass
    data["client"] = None
    data["session_string"] = None
    data["phone"] = None
    data["phone_code_hash"] = None

async def clear_flow(user_id: int, state: FSMContext, bot: Bot) -> None:
    expiry = EXPIRY_TASKS.pop(user_id, None)
    if expiry is not None and expiry is not asyncio.current_task():
        expiry.cancel()
    data = ACTIVE.pop(user_id, {})
    await disconnect_client(data)
    await delete_prompts(bot, user_id, data)
    await state.clear()

async def ask(bot: Bot, user_id: int, text: str, data: dict[str, Any]) -> None:
    prompt = await bot.send_message(user_id, text)
    data.setdefault("prompt_ids", []).append(prompt.message_id)

async def reset_expiry(user_id: int, state: FSMContext, bot: Bot) -> None:
    previous = EXPIRY_TASKS.pop(user_id, None)
    if previous is not None:
        previous.cancel()

    async def expire() -> None:
        try:
            await asyncio.sleep(600)
            if user_id in ACTIVE:
                await clear_flow(user_id, state, bot)
                await bot.send_message(user_id, "⌛ Generation timed out. Temporary login state was cleared. Use /generate to start again.")
        except asyncio.CancelledError:
            return

    EXPIRY_TASKS[user_id] = asyncio.create_task(expire())

async def finish_session(
    bot: Bot,
    user_id: int,
    state: FSMContext,
    session_string: str,
    engine: str,
) -> None:
    data = ACTIVE.get(user_id, {})
    data["session_string"] = session_string
    client = data.get("client")
    try:
        formatted = f"<code>{html.escape(session_string)}</code>"
        if engine == "pyrogram":
            from pyrogram.enums import ParseMode as PyroParseMode
            await client.send_message("me", formatted, parse_mode=PyroParseMode.HTML)
        else:
            await client.send_message("me", formatted, parse_mode="html")
    finally:
        # Drop references and disconnect; no session file/database is created.
        await clear_flow(user_id, state, bot)

    await bot.send_message(
        user_id,
        "✅ <b>Session generated successfully.</b>\n"
        "Your session was sent to this account's <b>Saved Messages</b> in monospace format.\n\n"
        "⚠️ Treat it like your account password. Anyone with this string can access your account.",
    )

async def start_login(user_id: int, engine: str) -> None:
    if engine == "pyrogram":
        from pyrogram import Client
        client = Client(
            name=f"sessionsgen_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
        )
    else:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(), API_ID, API_HASH)

    try:
        await client.connect()
    except Exception:
        try:
            await client.disconnect()
        except Exception:
            pass
        raise

    ACTIVE[user_id] = {
        "engine": engine,
        "client": client,
        "phone": None,
        "phone_code_hash": None,
        "prompt_ids": [],
        "session_string": None,
    }

async def handle_failure(message: Message, state: FSMContext, bot: Bot, reason: str) -> None:
    user_id = message.from_user.id if message.from_user else 0
    await clear_flow(user_id, state, bot)
    await message.answer(f"❌ {reason}\nUse /generate to start again.")

async def cmd_start(message: Message) -> None:
    if not message.from_user or not owner_only(message.from_user.id) or message.chat.type != "private":
        return
    await message.answer(
        "👋 <b>BIKA SESSION GEN</b>\n\n"
        "Choose an engine to generate a session for your own Telegram account.\n"
        "The session is delivered only to that account's Saved Messages.",
        reply_markup=engine_keyboard(),
    )

async def cmd_generate(message: Message) -> None:
    if not message.from_user or not owner_only(message.from_user.id) or message.chat.type != "private":
        return
    await message.answer("Choose your session engine:", reply_markup=engine_keyboard())

async def cmd_cancel(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not owner_only(message.from_user.id):
        return
    await safe_delete(message)
    await clear_flow(message.from_user.id, state, bot)
    await bot.send_message(message.chat.id, "Generation cancelled. Temporary login state cleared.")

async def choose_engine(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    user = callback.from_user
    if not owner_only(user.id) or callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Not authorized.", show_alert=True)
        return
    engine = callback.data.split(":", 1)[1]
    await callback.answer()
    await clear_flow(user.id, state, bot)
    try:
        await start_login(user.id, engine)
        await state.set_state(GenerateFlow.phone)
        await ask(
            bot,
            user.id,
            f"📱 <b>{engine.title()} session</b>\nSend your phone number with country code (example: <code>+1234567890</code>).",
            ACTIVE[user.id],
        )
        await reset_expiry(user.id, state, bot)
    except Exception as exc:
        log.warning("Could not start %s login (%s)", engine, type(exc).__name__)
        await clear_flow(user.id, state, bot)
        await bot.send_message(user.id, "Could not start login. Check API_ID/API_HASH and try again.")

async def receive_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not owner_only(message.from_user.id):
        return
    user_id = message.from_user.id
    phone = (message.text or "").strip()
    await safe_delete(message)
    data = ACTIVE.get(user_id)
    if not data or not phone.startswith("+") or not phone[1:].isdigit():
        await clear_flow(user_id, state, bot)
        await bot.send_message(user_id, "Invalid phone number. Use /generate to try again.")
        return
    try:
        client = data["client"]
        data["phone"] = phone
        if data["engine"] == "pyrogram":
            sent = await client.send_code(phone)
            data["phone_code_hash"] = sent.phone_code_hash
        else:
            sent = await client.send_code_request(phone)
            data["phone_code_hash"] = sent.phone_code_hash
        await state.set_state(GenerateFlow.code)
        await ask(
            bot,
            user_id,
            "🔐 Send the Telegram login code. You may enter digits separated by spaces.\n"
            "This message will be deleted after processing.",
            data,
        )
        await reset_expiry(user_id, state, bot)
    except Exception as exc:
        log.warning("Phone/code request failed (%s)", type(exc).__name__)
        await clear_flow(user_id, state, bot)
        await bot.send_message(user_id, "Could not request a login code. Check the phone number and try /generate again.")

async def receive_code(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not owner_only(message.from_user.id):
        return
    user_id = message.from_user.id
    code = "".join((message.text or "").split())
    await safe_delete(message)
    data = ACTIVE.get(user_id)
    if not data or not code:
        await clear_flow(user_id, state, bot)
        await bot.send_message(user_id, "Login flow expired. Use /generate to try again.")
        return
    client = data["client"]
    try:
        if data["engine"] == "pyrogram":
            await client.sign_in(data["phone"], data["phone_code_hash"], code)
            session_string = await client.export_session_string()
        else:
            await client.sign_in(
                phone=data["phone"],
                code=code,
                phone_code_hash=data["phone_code_hash"],
            )
            session_string = client.session.save()
        await finish_session(bot, user_id, state, session_string, data["engine"])
    except Exception as exc:
        from pyrogram.errors import SessionPasswordNeeded as PyroPasswordNeeded
        from telethon.errors import SessionPasswordNeededError as TelethonPasswordNeeded
        if isinstance(exc, (PyroPasswordNeeded, TelethonPasswordNeeded)):
            await state.set_state(GenerateFlow.password)
            await ask(
                bot,
                user_id,
                "🔒 Two-step verification is enabled. Send your 2FA password.\n"
                "It will be deleted after processing and is not written to a database or log.",
                data,
            )
            await reset_expiry(user_id, state, bot)
            return
        log.warning("Login code step failed (%s)", type(exc).__name__)
        await clear_flow(user_id, state, bot)
        await bot.send_message(user_id, "Login failed or code expired. Use /generate to try again.")

async def receive_password(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user or not owner_only(message.from_user.id):
        return
    user_id = message.from_user.id
    password = message.text or ""
    await safe_delete(message)
    data = ACTIVE.get(user_id)
    if not data:
        await clear_flow(user_id, state, bot)
        await bot.send_message(user_id, "Login flow expired. Use /generate to try again.")
        return
    try:
        client = data["client"]
        if data["engine"] == "pyrogram":
            await client.check_password(password)
            session_string = await client.export_session_string()
        else:
            await client.sign_in(password=password)
            session_string = client.session.save()
        await finish_session(bot, user_id, state, session_string, data["engine"])
    except Exception as exc:
        log.warning("2FA step failed (%s)", type(exc).__name__)
        await clear_flow(user_id, state, bot)
        await bot.send_message(user_id, "2FA verification failed. Use /generate to try again.")
    finally:
        password = ""

async def main() -> None:
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.register(cmd_cancel, Command("cancel"))
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_generate, Command("generate"))
    dp.callback_query.register(choose_engine, F.data.startswith("engine:"))
    dp.callback_query.register(cmd_cancel_callback, F.data == "cancel")
    dp.message.register(receive_phone, GenerateFlow.phone)
    dp.message.register(receive_code, GenerateFlow.code)
    dp.message.register(receive_password, GenerateFlow.password)
    log.info("SessionsGen bot starting (owner-only mode).")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=True)
    finally:
        for user_id, data in list(ACTIVE.items()):
            await disconnect_client(data)
            ACTIVE.pop(user_id, None)
        await bot.session.close()

async def cmd_cancel_callback(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not owner_only(callback.from_user.id):
        await callback.answer("Not authorized.", show_alert=True)
        return
    await callback.answer("Cancelled.")
    await clear_flow(callback.from_user.id, state, bot)
    if callback.message:
        await callback.message.answer("Generation cancelled. Temporary login state cleared.")

if __name__ == "__main__":
    asyncio.run(main())
