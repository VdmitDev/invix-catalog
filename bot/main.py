from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any

import httpx
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_TELEGRAM_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if value.strip().isdigit()
}
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com").strip()
BOT_WEBHOOK_BASE_URL = os.getenv("BOT_WEBHOOK_BASE_URL", "").rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-this-telegram-webhook-secret")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")

router = Router()


def catalog_keyboard():
    from aiogram.types import InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть каталог", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("У меня есть товары для вас 👋\nОткройте каталог, чтобы посмотреть доступные товары.", reply_markup=catalog_keyboard())
    user_id = message.from_user.id if message.from_user else None
    if user_id in ADMIN_TELEGRAM_IDS:
        await message.answer(
            "Для добавления товара нажмите «Создать товар» или используйте /create.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Создать товар")]],
                resize_keyboard=True,
                input_field_placeholder="Выберите действие",
            ),
        )


@router.message(Command("create"))
@router.message(F.text == "Создать товар")
async def prompt_create_product(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    if user_id not in ADMIN_TELEGRAM_IDS:
        await message.answer("Эта команда доступна только администратору.")
        return
    await message.answer("Пришлите фотографию товара и укажите его название в подписи к фото — одним сообщением.")


@router.message(F.photo)
async def create_product_from_photo(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id if message.from_user else None
    if user_id not in ADMIN_TELEGRAM_IDS:
        await message.answer("Добавлять товары может только администратор.")
        return

    title = (message.caption or "").strip()
    if not title:
        await message.answer("Добавьте название товара в подпись к фотографии и отправьте их одним сообщением.")
        return
    if len(title) > 200:
        await message.answer("Название должно быть не длиннее 200 символов.")
        return

    try:
        photo = message.photo[-1]
        telegram_file = await bot.get_file(photo.file_id)
        if not telegram_file.file_path:
            raise RuntimeError("Telegram did not return a file path")
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{telegram_file.file_path}"
        async with httpx.AsyncClient(timeout=45.0) as client:
            download = await client.get(file_url)
            download.raise_for_status()
            response = await client.post(
                f"{API_BASE_URL}/api/admin/products",
                headers={"X-Admin-Token": ADMIN_API_TOKEN},
                json={
                    "title": title,
                    "image_base64": base64.b64encode(download.content).decode("ascii"),
                    "source_chat_id": message.chat.id,
                    "source_message_id": message.message_id,
                },
            )
            response.raise_for_status()
        await message.answer("Товар сохранён в каталоге ✅")
    except httpx.HTTPStatusError as exc:
        detail: Any = "Не удалось сохранить товар. Проверьте изображение и попробуйте ещё раз."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        logger.warning("Product creation returned HTTP %s", exc.response.status_code)
        await message.answer(f"Не удалось добавить товар: {detail}")
    except Exception:
        logger.exception("Failed to create product from Telegram message")
        await message.answer("Произошла ошибка при добавлении товара. Попробуйте позже.")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def serve_health_only() -> None:
    """Keep container healthy while Telegram settings are not configured yet."""
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def main() -> None:
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is empty; serving health endpoint only. Configure it in .env to enable Telegram features.")
        await serve_health_only()
        return
    if not ADMIN_API_TOKEN:
        raise RuntimeError("ADMIN_API_TOKEN must be configured")
    if not BOT_WEBHOOK_BASE_URL:
        logger.warning("BOT_WEBHOOK_BASE_URL is empty. Configure a public HTTPS URL before using Telegram webhooks.")
        # Keep the process alive and healthy; no poller is started because multi-replica polling is unsafe.
        await serve_health_only()
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    app = web.Application()
    app.router.add_get("/health", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    await bot.set_webhook(
        url=f"{BOT_WEBHOOK_BASE_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=False,
    )
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()
    logger.info("Telegram webhook server listening on :8080%s", WEBHOOK_PATH)
    try:
        await asyncio.Event().wait()
    finally:
        # Do not delete the global webhook when one replica restarts; other replicas still use it.
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
