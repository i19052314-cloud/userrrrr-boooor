#  Mafia game module for @TrueMafiaBlackBot (Final Fixed Auto-Play + AI target selection)
import asyncio
import base64
import logging
import random
import re
from collections import deque

import aiohttp
from pyrogram import Client, filters
from pyrogram.raw import functions

from utils import modules_help, prefix
from utils.config import ai_base_url, ai_key, ai_model, owner_id
from utils.db import db

MAFIA_BOT = "TrueMafiaBlackBot"

log = logging.getLogger("mafia")

MAFIA_LINK_RE = re.compile(
    r"t\.me/TrueMafiaBlackBot\?start=([A-Za-z0-9_\-=]+)", re.IGNORECASE
)

# Ключевые слова для входа в игру или согласия
MAFIA_JOIN_RE = re.compile(
    r"(участв|участие|в игру|будете играть|хочешь сыграть|присоединиться|вступаешь|"
    r"принять участие|желаешь играть|начинаем игру|набор|поехали|играть)", re.IGNORECASE
)

# Опасные кнопки, на которые нельзя нажимать ни при каких условиях
MAFIA_DANGER_RE = re.compile(
    r"(выход|выйти|покинуть|меню|профиль|правила|отмена|назад|статистика|ошибка|настройки)", re.IGNORECASE
)

MAFIA_RECRUIT_RE = re.compile(
    r"(вед[её]тся\s+набор|набор\s+в\s+игру|ид[её]т\s+набор|открыт\s+набор|"
    r"начинаем\s+набор)", re.IGNORECASE
)

# Признаки начала нового раунда (день/ночь) — сбрасываем память недавних целей
ROUND_MARK_RE = re.compile(
    r"(наступ(ила|ает)\s+ночь|наступ(ил|ает)\s+день|день\s+№?\s*\d+|ночь\s+№?\s*\d+|"
    r"голосование\s+начал|начинается\s+голосование)", re.IGNORECASE
)

# Определение своей роли из сообщения бота (обычно приходит в ЛС при старте игры)
ROLE_RE = re.compile(r"ваша\s+роль\s*[:\-—]\s*([^\n<]{2,40})", re.IGNORECASE)

# Сколько последних выбранных кнопок помнить, чтобы не повторяться подряд
_RECENT_TARGETS_LIMIT = 3
# Случайная задержка перед кликом (сек)
_CLICK_DELAY_RANGE = (1.5, 4.0)
# Более короткая задержка после решения ИИ (сам запрос уже добавляет латентность)
_AI_CLICK_DELAY_RANGE = (0.5, 2.0)
# Сколько последних сообщений чата держим как контекст для ИИ
_CONTEXT_BUFFER_SIZE = 15
_AI_TIMEOUT = aiohttp.ClientTimeout(total=15)

_OWNER_FILTER = filters.user(int(owner_id)) if owner_id else filters.user(0)

_self_info_cache = {"id": None, "username": "", "first_name": ""}
_chat_context = {}  # {chat_id: deque[str]} — только в памяти, не персистится


def _debug_enabled():
    return db.get("custom.mafia", "debug", False)


def _dbg(msg):
    if _debug_enabled():
        log.info("[mafia debug] %s", msg)


def game_groups():
    saved = db.get("custom.mafia", "groups", [])
    return set(saved) if saved else set()


def add_game_group(gid):
    groups = game_groups()
    if gid not in groups:
        groups.add(gid)
        db.set("custom.mafia", "groups", list(groups))
        _dbg(f"добавлена игровая группа: {gid}")


def last_start():
    return db.get("custom.mafia", "last_start", None)


def remember_start(param):
    db.set("custom.mafia", "last_start", param)


def _is_from_mafia_bot(message) -> bool:
    fu = message.from_user
    return bool(fu and (fu.username or "").lower() == MAFIA_BOT.lower())


async def _self_info(client):
    """Кэшируем свои username/first_name, чтобы не выбирать самого себя как цель."""
    if _self_info_cache["id"] is None:
        try:
            me = await client.get_me()
            _self_info_cache["id"] = me.id
            _self_info_cache["username"] = (me.username or "").lower()
            _self_info_cache["first_name"] = (me.first_name or "").lower()
        except Exception as e:
            _dbg(f"не удалось получить свой профиль: {e}")
            _self_info_cache["id"] = -1
    return _self_info_cache


def _recent_targets(chat_id):
    data = db.get("custom.mafia", "recent_targets", {})
    return data.get(str(chat_id), [])


def _remember_target(chat_id, button_text):
    data = db.get("custom.mafia", "recent_targets", {})
    lst = data.get(str(chat_id), [])
    lst.append(button_text)
    data[str(chat_id)] = lst[-_RECENT_TARGETS_LIMIT:]
    db.set("custom.mafia", "recent_targets", data)


def _reset_recent_targets(chat_id):
    data = db.get("custom.mafia", "recent_targets", {})
    if str(chat_id) in data:
        del data[str(chat_id)]
        db.set("custom.mafia", "recent_targets", data)


async def _join_game(client, param=None):
    target = param or last_start()
    if not target:
        return
    try:
        await client.send_message(MAFIA_BOT, f"/start {target}")
        _dbg(f"отправлен /start {target} боту {MAFIA_BOT}")
    except Exception as e:
        _dbg(f"ошибка при отправке /start: {e}")


def _buttons(message):
    """Возвращает список (текст_кнопки, callback_data) как есть, без искажения байтов."""
    buttons = []
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            for b in row:
                text = b.text or ""
                data = b.callback_data
                if data:
                    buttons.append((text, data))
    return buttons


def _is_game_pm_or_group(_, __, message):
    if message.outgoing:
        return False
    if not _is_from_mafia_bot(message):
        return False
    gid = getattr(message.chat, "id", None)
    if message.chat.type.name == "private" or gid in game_groups():
        return True
    return False


def _find_link(message):
    m = MAFIA_LINK_RE.search(message.text or "")
    if m:
        return m
    if message.reply_markup and message.reply_markup.inline_keyboard:
        for row in message.reply_markup.inline_keyboard:
            for b in row:
                if b.url:
                    m = MAFIA_LINK_RE.search(b.url)
                    if m:
                        return m
    return None


def _filter_candidates(buttons, self_info):
    """Убирает 'опасные' кнопки и кнопки, где встречается наш собственный username/имя."""
    candidates = []
    for bt, data in buttons:
        if MAFIA_DANGER_RE.search(bt):
            continue
        low = bt.lower()
        if self_info["username"] and self_info["username"] in low:
            continue
        if self_info["first_name"] and self_info["first_name"] in low:
            continue
        candidates.append((bt, data))
    return candidates


def _choose_target_heuristic(candidates, recent):
    """Fallback: случайный выбор среди кандидатов, стараясь не повторять недавние."""
    if not candidates:
        return None
    fresh = [c for c in candidates if c[0] not in recent]
    pool = fresh if fresh else candidates
    return random.choice(pool)


def _build_ai_url() -> str:
    base_url = (ai_base_url or "").rstrip("/")
    if "openrouter.ai" in base_url and not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return f"{base_url}/chat/completions"


async def _ai_choose_target(candidates, context_lines, role=None):
    """
    Просит ИИ выбрать номер кнопки из списка кандидатов, опираясь на последние
    сообщения чата и (если известна) свою роль. Возвращает индекс в candidates
    или None, если ответ не удалось получить/распознать — тогда вызывающий код
    обязан откатиться на эвристику.
    """
    if not ai_key or not ai_base_url or not candidates:
        return None

    options_text = "\n".join(f"{i + 1}. {bt}" for i, (bt, _) in enumerate(candidates))
    context_text = "\n".join(context_lines) if context_lines else "(сообщений пока нет)"
    role_line = f"Твоя роль в игре: {role}.\n" if role else ""

    system_prompt = (
        "Ты играешь в текстовую игру 'Мафия' в Telegram-чате. Нужно выбрать РОВНО ОДИН "
        "вариант действия (голосование днём или ночное действие) из пронумерованного списка, "
        "основываясь на последних сообщениях чата. Ответь СТРОГО одним числом — номером "
        "выбранного варианта, без пояснений и лишнего текста."
    )
    user_prompt = (
        f"{role_line}"
        f"Последние сообщения в чате:\n{context_text}\n\n"
        f"Варианты действия:\n{options_text}\n\n"
        "Номер выбранного варианта:"
    )

    headers = {
        "Authorization": f"Bearer {ai_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/moon-userbot",
        "X-Title": "Moon Userbot",
    }
    payload = {
        "model": ai_model or "stealth/ox-alpha",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 5,
    }

    try:
        async with aiohttp.ClientSession(timeout=_AI_TIMEOUT) as session:
            async with session.post(_build_ai_url(), json=payload, headers=headers) as resp:
                if resp.status != 200:
                    _dbg(f"ИИ вернул HTTP {resp.status}")
                    return None
                data = await resp.json()
                answer = data["choices"][0]["message"]["content"]
    except (aiohttp.ClientError, KeyError, IndexError, TypeError, ValueError) as e:
        _dbg(f"запрос к ИИ не удался: {e}")
        return None

    m = re.search(r"\d+", answer or "")
    if not m:
        _dbg(f"не удалось распознать число в ответе ИИ: {answer!r}")
        return None

    idx = int(m.group()) - 1
    if 0 <= idx < len(candidates):
        return idx

    _dbg(f"ИИ вернул номер вне диапазона: {idx + 1}")
    return None


async def _force_click(client, message, button_text, callback_data):
    try:
        await message.click(button_text)
        _dbg(f"клик через message.click: {button_text!r}")
        return
    except Exception as e:
        _dbg(f"message.click не удался ({e}), пробуем raw API")

    try:
        c_data = callback_data.encode("utf-8") if isinstance(callback_data, str) else callback_data
        chat_id = message.chat.id
        msg_id = message.id

        if chat_id < 0:
            peer = await client.resolve_peer(chat_id)
        else:
            user = await client.get_users(chat_id)
            peer = await client.resolve_peer(user.id)

        await client.invoke(
            functions.messages.GetBotCallbackAnswer(peer=peer, msg_id=msg_id, data=c_data)
        )
        _dbg(f"клик через raw API: {button_text!r}")
    except Exception as e:
        _dbg(f"raw API клик не удался: {e}")


@Client.on_message(filters.command("mafia", prefix) & filters.me)
async def mafia_join(client, message):
    lt = last_start()
    if lt:
        await message.edit("<b>⏳ Пробуем войти в последнюю игру...</b>")
        await _join_game(client, lt)
    else:
        await message.edit("<b>❌ Бот еще не поймал ссылку на игру. Дождитесь нового набора в чате!</b>")
    await message.delete()


@Client.on_message(filters.command(["mafiagroup", "mafiachat"], prefix) & filters.me)
async def mafia_set_group(client, message):
    if message.chat.type.name in ("group", "supergroup"):
        add_game_group(message.chat.id)
        await message.reply_text(f"<b>Чат добавлен в игровые:</b> <code>{message.chat.id}</code>")
    else:
        await message.reply_text(f"<b>Активные группы:</b> <code>{list(game_groups())}</code>")


@Client.on_message(_OWNER_FILTER & filters.text)
async def mafia_autolink(client, message):
    m = MAFIA_LINK_RE.search(message.text or "")
    if not m:
        return

    remember_start(m.group(1))
    await _join_game(client, m.group(1))

    if not m.group(1).startswith("G_"):
        return

    try:
        raw = m.group(1)[2:]
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        gid_str = decoded.split("_")[0]
        add_game_group(int(gid_str))
    except Exception as e:
        _dbg(f"не удалось разобрать id группы из start-параметра: {e}")


@Client.on_message(filters.group & filters.text & ~filters.me)
async def mafia_autojoin(client, message):
    # Реагируем ТОЛЬКО на сообщения от самого мафия-бота — иначе можно случайно
    # кликнуть по кнопкам постороннего (в т.ч. скам) бота в группе.
    if not _is_from_mafia_bot(message):
        return

    gid = message.chat.id
    text = message.text or message.caption or ""
    m = _find_link(message)
    is_recruit = bool(text and MAFIA_RECRUIT_RE.search(text))

    if m or is_recruit:
        add_game_group(gid)
        if m:
            remember_start(m.group(1))
            await _join_game(client, m.group(1))
            return
        if is_recruit:
            for bt, data in _buttons(message):
                if MAFIA_JOIN_RE.search(bt):
                    await _force_click(client, message, bt, data)
                    return


@Client.on_message(filters.group & filters.text & ~filters.me)
async def mafia_context_collector(client, message):
    """Копит последние сообщения игроков в игровых чатах — контекст для ИИ."""
    gid = message.chat.id
    if gid not in game_groups():
        return
    if _is_from_mafia_bot(message):
        return  # служебные сообщения самого бота в контекст не нужны

    sender = message.from_user.first_name if message.from_user else "Игрок"
    buf = _chat_context.setdefault(gid, deque(maxlen=_CONTEXT_BUFFER_SIZE))
    buf.append(f"{sender}: {message.text}")


# Обработка ночных ходов (роли, маньяк, доктор), голосований и ошибок
@Client.on_message(filters.create(_is_game_pm_or_group))
async def mafia_game(client, message):
    text = message.text or message.caption or ""
    chat_id = message.chat.id

    if any(err in text.lower() for err in ["игра уже началась", "ошибка", "возможно игра не запущена"]):
        db.set("custom.mafia", "last_start", None)
        _dbg(f"сброшен last_start из-за сообщения: {text[:80]!r}")
        return

    role_match = ROLE_RE.search(text) if text else None
    if role_match:
        role_val = role_match.group(1).strip()
        db.set("custom.mafia", "role", role_val)
        _dbg(f"определена роль: {role_val}")

    if text and ROUND_MARK_RE.search(text):
        _reset_recent_targets(chat_id)
        _dbg("обнаружен новый раунд, память целей сброшена")

    btns = _buttons(message)
    if not btns:
        return

    for bt, data in btns:
        if MAFIA_JOIN_RE.search(bt):
            await _force_click(client, message, bt, data)
            return

    self_info = await _self_info(client)
    candidates = _filter_candidates(btns, self_info)
    if not candidates:
        return

    chosen = None

    if ai_key and ai_base_url:
        try:
            context_lines = list(_chat_context.get(chat_id, []))
            role = db.get("custom.mafia", "role", None)
            idx = await _ai_choose_target(candidates, context_lines, role)
        except Exception as e:
            _dbg(f"непредвиденная ошибка при обращении к ИИ: {e}")
            idx = None

        if idx is not None:
            chosen = candidates[idx]
            _dbg(f"ИИ выбрал: {chosen[0]!r}")
            await asyncio.sleep(random.uniform(*_AI_CLICK_DELAY_RANGE))
        else:
            _dbg("ИИ не дал валидный ответ, откат на эвристику")

    if chosen is None:
        recent = _recent_targets(chat_id)
        chosen = _choose_target_heuristic(candidates, recent)
        if not chosen:
            return
        await asyncio.sleep(random.uniform(*_CLICK_DELAY_RANGE))

    bt, data = chosen
    await _force_click(client, message, bt, data)
    _remember_target(chat_id, bt)
    _dbg(f"итоговый клик: {bt!r}")


@Client.on_message(filters.command("mafiadebug", prefix) & filters.me)
async def mafia_debug(_, message):
    cur = db.get("custom.mafia", "debug", False)
    db.set("custom.mafia", "debug", not cur)
    state = "on" if not cur else "off"
    await message.reply_text(f"<b>Mafia debug log: {state}</b>")


modules_help["mafia"] = {
    "mafia": "Join latest mafia game",
    "mafiagroup": "Add current chat to active mafia groups",
    "mafiadebug": "Toggle mafia event logging",
}
