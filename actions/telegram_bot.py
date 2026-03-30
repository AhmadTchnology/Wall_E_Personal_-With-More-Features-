"""
actions/telegram_bot.py — Wall-E Telegram Bot (NVIDIA NIM)

Text messages  → NVIDIA NIM /v1/chat/completions
Screenshots    → mss capture → save to SCREENSHOT_DIR → send photo
Voice commands → unchanged (Gemini in main.py)

Config loaded from server/.env:
  TELEGRAM_BOT_TOKEN, NVIDIA_API_KEY, NVIDIA_EMBED_URL (base),
  NVIDIA_CHAT_MODEL, SCREENSHOT_DIR
"""

import os
import sys
import threading
import logging
from pathlib import Path
from datetime import datetime

import httpx
import mss
import mss.tools

from dotenv import load_dotenv

logger = logging.getLogger("wall-e-telegram")

# ── Paths ─────────────────────────────────────────────────

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE_DIR = _get_base_dir()
_ENV_PATH = _BASE_DIR / "server" / ".env"

# ── Config ────────────────────────────────────────────────

def _load_config() -> dict:
    """Load config from server/.env and return as dict."""
    load_dotenv(_ENV_PATH, override=True)
    return {
        "bot_token":      os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "nvidia_api_key": os.getenv("NVIDIA_API_KEY", ""),
        "nvidia_base_url": os.getenv("NVIDIA_EMBED_URL", "https://integrate.api.nvidia.com/v1").rstrip("/"),
        "chat_model":     os.getenv("NVIDIA_CHAT_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"),
        "screenshot_dir": os.getenv("SCREENSHOT_DIR", str(Path.home() / "Pictures" / "Wall_E_Screenshots")),
    }

# ── Screenshot ────────────────────────────────────────────

_SCREENSHOT_KEYWORDS = [
    "screenshot", "screen", "ekran", "görüntü",
    "ekran görüntüsü", "capture", "snap",
]


def _capture_screenshot() -> bytes:
    """Capture full screen as JPEG bytes (reuses same mss logic as screen_processor.py)."""
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(png_bytes))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except ImportError:
        return png_bytes


def _save_screenshot(screenshot_bytes: bytes, screenshot_dir: str) -> Path:
    """Save screenshot to the configured directory. Returns the file path."""
    folder = Path(screenshot_dir)
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "jpg" if screenshot_bytes[:2] == b'\xff\xd8' else "png"
    file_path = folder / f"WallE_Screenshot_{timestamp}.{ext}"
    file_path.write_bytes(screenshot_bytes)

    logger.info(f"Screenshot saved: {file_path}")
    return file_path


def _is_screenshot_request(text: str) -> bool:
    """Check if the message is asking for a screenshot."""
    lower = text.lower()
    return any(kw in lower for kw in _SCREENSHOT_KEYWORDS)

# ── NVIDIA NIM Chat ───────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are Wall-E, a sharp and efficient AI assistant. "
    "Calm, direct, professional. Address the user as 'sir'. "
    "Keep responses concise (2-3 sentences max). "
    "Respond in the same language the user writes in."
)


def _chat_nvidia_nim(user_text: str, config: dict) -> str:
    """Send a chat completion request to NVIDIA NIM and return the response."""
    url = f"{config['nvidia_base_url']}/chat/completions"

    headers = {
        "Authorization": f"Bearer {config['nvidia_api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config["chat_model"],
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    except httpx.HTTPStatusError as e:
        logger.error(f"NIM API error {e.response.status_code}: {e.response.text[:200]}")
        return f"⚠️ AI service error (HTTP {e.response.status_code}). Please try again."
    except Exception as e:
        logger.error(f"NIM request failed: {e}")
        return "⚠️ Could not reach the AI service. Please try again later."

# ── Telegram Handlers ─────────────────────────────────────

def _build_app(config: dict):
    """Build and return the Telegram Application with handlers."""
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Hello sir, I'm Wall-E.\n\n"
            "Send me any message and I'll respond.\n"
            "Send /screenshot or say 'send me a screenshot' to capture your screen."
        )

    async def cmd_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📸 Capturing screen...")
        try:
            img_bytes = _capture_screenshot()
            file_path = _save_screenshot(img_bytes, config["screenshot_dir"])
            await update.message.reply_photo(
                photo=file_path.read_bytes(),
                caption=f"🖥️ Screenshot saved to:\n`{file_path}`",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            await update.message.reply_text(f"⚠️ Screenshot failed: {e}")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text or ""
        if not text.strip():
            return

        # Check if it's a screenshot request
        if _is_screenshot_request(text):
            await cmd_screenshot(update, context)
            return

        # Forward to NVIDIA NIM
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        reply = _chat_nvidia_nim(text, config)
        await update.message.reply_text(reply)

    app = Application.builder().token(config["bot_token"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("screenshot", cmd_screenshot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app

# ── Entry Point ───────────────────────────────────────────

def start_telegram_bot():
    """Load config from server/.env, build the bot, and start polling in a daemon thread."""
    config = _load_config()

    if not config["bot_token"] or config["bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("Telegram bot token not configured — skipping bot startup")
        return

    if not config["nvidia_api_key"]:
        logger.warning("NVIDIA API key not configured — Telegram bot cannot start")
        return

    def _run():
        import asyncio

        async def _poll():
            app = _build_app(config)
            logger.info(
                f"Telegram bot starting (model: {config['chat_model']}, "
                f"screenshots: {config['screenshot_dir']})"
            )
            async with app:
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)
                # Keep running until the thread is killed
                stop_event = asyncio.Event()
                await stop_event.wait()

        asyncio.run(_poll())

    thread = threading.Thread(target=_run, daemon=True, name="telegram-bot")
    thread.start()
    print(f"[Wall-E] 🤖 Telegram bot started (model: {config['chat_model']})")
