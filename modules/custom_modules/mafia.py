#  Mafia game module for @TrueMafiaBlackBot
import base64
import random
import re
import time

from pyrogram import Client, filters

from utils import modules_help, prefix
from utils.config import mafia_groups, mafia_start, owner_id

MAFIA_BOT = "TrueMafiaBlackBot"
MAFIA_LINK_RE = re.compile(
    r"t\.me/TrueMafiaBlackBot\?start=([A-Za-z0-9_\-=]+)", re.IGNORECASE
)
JOIN_PHRASE_RE = re.compile(
    r"вед(ё|е)тся\s+набор\s+в\s+игру", re.IGNORECASE
)
MAFIA_JOIN_RE = re.compile(
    r"(участв|участие|в игру|будете играть|хочешь сыграть|присоединиться|вступаешь|"
    r"принять участие|желаешь играть|начинаем игру|набор|поехали|играть)", re.IGNORECASE
)
MAFIA_PHASE_RE = re.compile(
    r"(голосован|выберите|ваш голос|за кого|выгоняем|день|ночь|мафия|убит|выбыл|"
    r"просыпается|ваш ход)", re.IGNORECASE
)
_OWNER_FILTER = filters.user(int(owner_id)) if owner_id else filters.user(0)


def _decode_group(param):
    try:
        if param.startswith("G_"):
            raw = base64.urlsafe_b64decode(param[2:] + "==").decode()
            return int(raw.split("_")[0])
    except Exception:
        pass
    return None


def _buttons(message):
    buttons = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            for b in row:
                buttons.append((b.text or "", b.callback_data or b.url or ""))
    return buttons


def _in_mafia_groups(_, __, message):
    return message.chat and message.chat.id in mafia_groups


@Client.on_message(filters.command("mafia", prefix) & filters.me)
async def mafia_join(client, message):
    await client.send_message(MAFIA_BOT, f"/start {mafia_start}")
    await message.delete()


_last_autojoin = {}
AUTOJOIN_COOLDOWN = 300


@Client.on_message(filters.group & filters.text & ~filters.me)
async def mafia_autojoin(client, message):
    text = message.text or ""
    now = time.time()
    key = message.chat.id

    if _last_autojoin.get(key, 0) + AUTOJOIN_COOLDOWN > now:
        return

    param = None
    m = MAFIA_LINK_RE.search(text)
    if m:
        param = m.group(1)
        gid = _decode_group(param)
        if gid:
            mafia_groups.add(gid)
    elif JOIN_PHRASE_RE.search(text):
        param = mafia_start

    if not param:
        return

    _last_autojoin[key] = now
    try:
        await client.send_message(MAFIA_BOT, f"/start {param}")
        await message.reply("<b>🤖 Автоматически вступаю в игру...</b>")
    except Exception as e:
        from utils.scripts import format_exc
        await message.reply(format_exc(e))


@Client.on_message(filters.user(MAFIA_BOT) & filters.create(_in_mafia_groups))
async def mafia_game(client, message):
    text = message.text or message.caption or ""
    btns = _buttons(message)

    for bt, data in btns:
        if MAFIA_JOIN_RE.search(bt):
            try:
                await message.click(bt)
            except Exception:
                await client.request_callback_answer(message.id, data)
            return

    if btns and MAFIA_PHASE_RE.search(text):
        bt, data = random.choice(btns)
        try:
            await message.click(bt)
        except Exception:
            await client.request_callback_answer(message.id, data)
        return

    if text or btns:
        await client.send_message(
            "me",
            f"[Mafia] {message.chat.title}:\n{text}\nBTN: {btns}",
        )


modules_help["mafia"] = {
    "mafia": "Join/start mafia game in owner group",
}