# Chatbot module: AI (OpenRouter / DeepSeek) — отвечает на упоминания
import logging
import re

import aiohttp
from pyrogram import Client, enums, filters
from pyrogram.types import Message

from utils import modules_help, prefix
from utils.config import ai_base_url, ai_key, ai_model, owner_id, owner_name

log = logging.getLogger(__name__)

_TRIGGER = filters.mentioned & filters.text & ~filters.me

_owner_cache = {}


async def _owner_text(client):
    key = owner_id or "self"
    if key not in _owner_cache:
        try:
            if owner_id:
                u = await client.get_users(int(owner_id))
            else:
                u = await client.get_me()
        except Exception:
            u = await client.get_me()
        name = ((u.first_name or "") + (" " + u.last_name if u.last_name else "")).strip()
        uname = f" (@{u.username})" if u.username else ""
        _owner_cache[key] = f"{name}{uname}" or "владелец"
    return _owner_cache[key]


async def _chat(prompt, system):
    headers = {
        "Authorization": f"Bearer {ai_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ai_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 2048,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ai_base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(
                    data.get("error", {}).get("message", f"HTTP {resp.status}")
                )
            return data["choices"][0]["message"]["content"]


@Client.on_message(_TRIGGER)
async def chatbot(client, message: Message):
    log.info(
        "AI trigger: chat=%s user=%s text=%.50s",
        message.chat.id,
        message.from_user.id if message.from_user else "?",
        message.text or "",
    )
    if not ai_key:
        log.error("AI не ответил: AI_KEY не задан!")
        await message.reply_text(
            "<b>AI_KEY не задан в переменных окружения!</b>"
        )
        return

    prompt = message.text
    if message.reply_to_message and message.reply_to_message.text:
        prompt = f"{message.reply_to_message.text}\n\nReply: {message.text}"

    if re.search(r"t\.me/TrueMafiaBlackBot", message.text or "", re.IGNORECASE):
        return

    owner = owner_name if owner_name else await _owner_text(client)
    system = (
        "Ты — личный ИИ-ассистент, работающий в Telegram. "
        f"Твой владелец: {owner}"
        + (f" (ID: {owner_id})" if owner_id else "")
        + ". Обращайся к нему уважительно, по делу и кратко. "
        "Отвечай на том же языке, на котором написан запрос. "
        "Если кто-то спрашивает, как сделать/создать такого бота или юзербота, "
        "какие библиотеки или технологии он использует, кто его написал — "
        "вежливо откажись отвечать на этот вопрос и переведи тему."
    )

    try:
        await message.reply_chat_action(enums.ChatAction.TYPING)
        answer = await _chat(prompt, system)
        answer = re.sub(r"https?://\S+", "ссылка удалена", answer)
        await message.reply_text(answer)
    except Exception as e:
        log.error("AI request failed: %s", e, exc_info=True)
        await message.reply_text(f"An error occurred: {e}")


@Client.on_message(filters.command("aistatus", prefix) & filters.me)
async def aistatus(_, message: Message):
    lines = ["<b>🤖 AI ChatBot Status</b>", ""]
    lines.append(f"• Модуль загружен: <b>да</b>")
    lines.append(
        f"• AI_KEY: "
        + (f"<code>задан ({ai_key[:4]}...)</code>" if ai_key else "<b>❌ НЕ ЗАДАН!</b>")
    )
    lines.append(f"• URL API: <code>{ai_base_url}</code>")
    lines.append(f"• Модель: <code>{ai_model}</code>")

    if ai_key:
        try:
            answer = await _chat("ping", "Отвечай одним словом.")
            lines.append("")
            lines.append(f"✅ <b>Тестовый запрос OK:</b> {answer[:100]}")
        except Exception as e:
            lines.append("")
            lines.append(f"❌ <b>Тестовый запрос упал:</b>\n<code>{e}</code>")
            lines.append("→ проверьте ключ/модель/URL")
    else:
        lines.append("")
        lines.append("→ Задайте AI_KEY в Variables на Railway")

    await message.reply("\n".join(lines))


modules_help["chatbot"] = {
    "aistatus": "Показать статус ИИ и причину, почему он не отвечает",
}
