"""
actions/telegram_bot.py — Wall-E Telegram Bot (NVIDIA NIM + shared tools)

Uses the SAME TOOL_DECLARATIONS and _call_tool() as the main Gemini voice app.
Gemini tool format is auto-converted to OpenAI format via tool_bridge.py.

Text messages  → NVIDIA NIM /v1/chat/completions (with function calling)
Screenshots    → mss capture → save to SCREENSHOT_DIR → send photo
Voice commands → unchanged (Gemini in main.py)

Config loaded from server/.env
"""

import os
import sys
import json
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
    load_dotenv(_ENV_PATH, override=True)
    return {
        "bot_token":       os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "nvidia_api_key":  os.getenv("NVIDIA_API_KEY", ""),
        "nvidia_base_url": os.getenv("NVIDIA_EMBED_URL", "https://integrate.api.nvidia.com/v1").rstrip("/"),
        "chat_model":      os.getenv("NVIDIA_CHAT_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"),
        "screenshot_dir":  os.getenv("SCREENSHOT_DIR", str(Path.home() / "Pictures" / "Wall_E_Screenshots")),
    }

# ── Shared tools (import from main project) ───────────────

def _get_openai_tools() -> list[dict]:
    """Import the Gemini TOOL_DECLARATIONS from main.py and convert to OpenAI format."""
    sys.path.insert(0, str(_BASE_DIR))
    from main import TOOL_DECLARATIONS
    from actions.tool_bridge import gemini_to_openai_tools
    return gemini_to_openai_tools(TOOL_DECLARATIONS)


def _execute_tool(name: str, arguments: dict) -> str:
    """Dispatch a tool call using the existing executor from agent/executor.py."""
    sys.path.insert(0, str(_BASE_DIR))
    from agent.executor import _call_tool
    try:
        result = _call_tool(name, arguments, speak=None)
        return str(result) if result else "Done."
    except Exception as e:
        logger.error(f"Tool '{name}' failed: {e}")
        return f"Tool error: {e}"

# ── Screenshot helpers ────────────────────────────────────

_SCREENSHOT_KEYWORDS = [
    "screenshot", "screen", "ekran", "görüntü",
    "ekran görüntüsü", "capture", "snap",
]


def _capture_screenshot() -> bytes:
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
    folder = Path(screenshot_dir)
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "jpg" if screenshot_bytes[:2] == b'\xff\xd8' else "png"
    file_path = folder / f"WallE_Screenshot_{timestamp}.{ext}"
    file_path.write_bytes(screenshot_bytes)
    logger.info(f"Screenshot saved: {file_path}")
    return file_path


def _is_screenshot_request(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _SCREENSHOT_KEYWORDS)

# ── NVIDIA NIM Chat with Tool Calling ─────────────────────

_SYSTEM_PROMPT = (
    "You are Wall-E, a sharp and efficient AI assistant. "
    "Calm, direct, professional. Address the user as 'sir'. "
    "Keep responses concise (2-3 sentences max). "
    "Respond in the same language the user writes in. "
    "You have access to tools to control the computer, search the web, "
    "manage files, open apps, and more. Use them when appropriate. "
    "Always call the appropriate tool — never simulate or guess results. "
    "If the task can be done in ONE action, use the specific tool. "
    "If it needs multiple steps, use agent_task."
)

MAX_TOOL_ROUNDS = 5  # Prevent infinite tool-call loops


def _chat_with_tools(user_text: str, config: dict, openai_tools: list[dict]) -> str:
    """
    Send message to NVIDIA NIM with function calling.
    If the model calls a tool, execute it and feed the result back.
    Loops until the model returns a text response or MAX_TOOL_ROUNDS.
    """
    url = f"{config['nvidia_base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['nvidia_api_key']}",
        "Content-Type": "application/json",
    }

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        payload = {
            "model": config["chat_model"],
            "messages": messages,
            "tools": openai_tools,
            "tool_choice": "auto",
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"NIM API error {e.response.status_code}: {e.response.text[:200]}")
            return f"⚠️ AI service error (HTTP {e.response.status_code}). Please try again."
        except Exception as e:
            logger.error(f"NIM request failed: {e}")
            return "⚠️ Could not reach the AI service. Please try again later."

        data = response.json()
        choice = data["choices"][0]
        msg = choice["message"]

        # If no tool calls, return the text response
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content", "Done.").strip()

        # Append assistant message with tool calls
        messages.append(msg)

        # Execute each tool call and feed results back
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                func_args = {}

            logger.info(f"Tool call: {func_name}({func_args})")
            result = _execute_tool(func_name, func_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(result)[:2000],  # Cap result length
            })

    # If we exhausted rounds, return what we have
    return "I completed the actions. Let me know if you need anything else, sir."

# ── Telegram Handlers ─────────────────────────────────────

def _build_app(config: dict, openai_tools: list[dict]):
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
            "I can also control your computer, search the web, manage files, and more.\n"
            "Send /screenshot to capture your screen."
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

        # Direct screenshot request → capture and send
        if _is_screenshot_request(text):
            await cmd_screenshot(update, context)
            return

        # Forward to NVIDIA NIM with tool calling
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
        reply = _chat_with_tools(text, config, openai_tools)

        # Split long replies (Telegram limit: 4096 chars)
        if len(reply) > 4000:
            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i:i+4000])
        else:
            await update.message.reply_text(reply)

    app = Application.builder().token(config["bot_token"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("screenshot", cmd_screenshot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app

# ── Entry Point ───────────────────────────────────────────

def start_telegram_bot():
    """Load config, convert tools, start polling in a daemon thread."""
    config = _load_config()

    if not config["bot_token"] or config["bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("Telegram bot token not configured — skipping")
        return

    if not config["nvidia_api_key"]:
        logger.warning("NVIDIA API key not configured — Telegram bot cannot start")
        return

    # Convert Gemini tools to OpenAI format (once at startup)
    openai_tools = _get_openai_tools()
    logger.info(f"Loaded {len(openai_tools)} tools for Telegram bot")

    def _run():
        import asyncio

        async def _poll():
            app = _build_app(config, openai_tools)
            logger.info(
                f"Telegram bot starting (model: {config['chat_model']}, "
                f"tools: {len(openai_tools)}, screenshots: {config['screenshot_dir']})"
            )
            async with app:
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)
                stop_event = asyncio.Event()
                await stop_event.wait()

        asyncio.run(_poll())

    thread = threading.Thread(target=_run, daemon=True, name="telegram-bot")
    thread.start()
    print(f"[Wall-E] 🤖 Telegram bot started (model: {config['chat_model']}, tools: {len(openai_tools)})")
