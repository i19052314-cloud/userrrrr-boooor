#  Mafia game module for @TrueMafiaBlackBot
import base64
import random
import re

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
    await message.delete()

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        arg = args[1].strip()
        try:
            target = int(arg)
        except ValueError:
            target = arg.lstrip("@")
        try:
            chat_obj = await client.get_chat(target)
            target_id = chat_obj.id
        except Exception as e:
            await client.send_message(message.chat.id, f"<b>Не нашёл чат:</b> <code>{e}</code>")
            return
    else:
        target_id = message.chat.id

    found_param = None
    async for msg in client.get_chat_history(target_id, limit=200):
        text = msg.text or msg.caption or ""
        m = MAFIA_LINK_RE.search(text)
        if not m and msg.reply_markup and getattr(msg.reply_markup, "inline_keyboard", None):
            for row in msg.reply_markup.inline_keyboard:
                for b in row:
                    mm = MAFIA_LINK_RE.search(getattr(b, "url", "") or "")
                    if mm:
                        m = mm
                        break
                if m:
                    break
        if m:
            found_param = m.group(1)

    if not found_param:
        await client.send_message(
            message.chat.id,
            "<b>❌ Свежих ссылок на игру в этом чате нет.</b>\n"
            "Как только появится «Ведётся набор в игру» или ссылка — вступлю автоматически.",
        )
        return

    gid = _decode_group(found_param)
    if gid:
        mafia_groups.add(gid)

    try:
        await client.send_message(MAFIA_BOT, f"/start {found_param}")
        await client.send_message(
            message.chat.id,
            "<b>✅ Вступил в игру по свежей ссылке из этого чата.</b>",
        )
    except Exception as e:
        from utils.scripts import format_exc
        await client.send_message("me", f"[Mafia .mafia error]\n{format_exc(e)}")


@Client.on_message(filters.group & filters.text & ~filters.me)
async def mafia_autojoin(client, message):
    text = message.text or ""

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

    try:
        await client.send_message(MAFIA_BOT, f"/start {param}")
    except Exception as e:
        from utils.scripts import format_exc
        await client.send_message("me", f"[Mafia autojoin error]\n{format_exc(e)}")


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