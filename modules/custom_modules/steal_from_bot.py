"""
Модуль для Moon-Userbot: кража фильмов с автоматическим поиском и нажатием кнопок
by @loveaideep
"""

import asyncio
import sqlite3
import re
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.enums import ParseMode

LOGGER = logging.getLogger(__name__)
DB_PATH = "movies.db"

# ===== КОНФИГ =====
TARGET_BOT = "NitokinMedia23Bot"  # 👈 ИМЯ БОТА, У КОТОРОГО ВОРУЕМ
TARGET_CHANNEL = "your_channel"  # 👈 ТВОЙ КАНАЛ
SEARCH_DELAY = 5  # Задержка между запросами

# ===== БАЗА =====
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_ru TEXT,
                title_en TEXT,
                year TEXT,
                imdb_id TEXT,
                imdb_rating TEXT,
                poster_file_id TEXT,
                video_file_id TEXT,
                source_bot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

def save_movie(data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO movies (title_ru, title_en, year, imdb_id, imdb_rating, poster_file_id, video_file_id, source_bot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("title_ru"),
            data.get("title_en"),
            data.get("year"),
            data.get("imdb_id"),
            data.get("imdb_rating"),
            data.get("poster_file_id"),
            data.get("video_file_id"),
            data.get("source_bot")
        ))
        conn.commit()

def movie_exists(title):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM movies WHERE title_ru LIKE ? OR title_en LIKE ?", (f"%{title}%", f"%{title}%"))
        return cur.fetchone() is not None

def get_movies_count():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM movies")
        return cur.fetchone()[0]

# ===== ФУНКЦИИ =====
async def extract_movie(text):
    data = {}
    m = re.search(r'^(.*?)\s*/\s*(.*?)\s*\((\d{4})\)', text)
    if m:
        data["title_ru"] = m.group(1).strip()
        data["title_en"] = m.group(2).strip()
        data["year"] = m.group(3)
    m = re.search(r'imdb\.com/title/(tt\d+)', text)
    if m:
        data["imdb_id"] = m.group(1)
    m = re.search(r'(\d+\.\d+)/10\s*⭐', text)
    if m:
        data["imdb_rating"] = m.group(1)
    return data

async def steal_from_bot(client, bot_name, search_query):
    """
    Основная функция кражи:
    1. Пишет боту search_query
    2. Ждёт ответ с кнопками
    3. Нажимает на кнопку с фильмом
    4. Забирает постер и видео
    5. Сохраняет в БД и канал
    """
    LOGGER.info(f"🎯 Ищу фильм: {search_query}")
    
    try:
        # 1. Отправляем запрос боту
        await client.send_message(bot_name, search_query)
        await asyncio.sleep(3)  # Ждём ответ
        
        # 2. Получаем последние ответы бота
        msgs = []
        async for msg in client.get_chat_history(bot_name, limit=10):
            if msg.from_user and msg.from_user.is_bot:
                msgs.append(msg)
        
        # 3. Ищем сообщение с кнопками и текстом
        target_msg = None
        for msg in msgs:
            if msg.text and msg.reply_markup and "IMDb" in msg.text:
                target_msg = msg
                break
        
        if not target_msg:
            LOGGER.warning(f"⚠️ Нет ответа от бота на запрос: {search_query}")
            return False
        
        # 4. Ищем кнопку с фильмом (она может быть подписана как "Скачать", "Download" или просто название)
        clicked = False
        if target_msg.reply_markup:
            for row in target_msg.reply_markup.inline_keyboard:
                for btn in row:
                    # Проверяем, что кнопка ведёт на фильм
                    btn_text = btn.text.lower()
                    if ("скачать" in btn_text or "download" in btn_text or 
                        search_query.lower() in btn_text or "смотреть" in btn_text):
                        LOGGER.info(f"🔘 Нажимаю кнопку: {btn.text}")
                        await client.request_callback_answer(
                            chat_id=bot_name,
                            message_id=target_msg.id,
                            callback_data=btn.callback_data
                        )
                        clicked = True
                        await asyncio.sleep(3)  # Ждём ответ после нажатия
                        break
                if clicked:
                    break
        
        if not clicked:
            LOGGER.warning(f"⚠️ Не найдено кнопок для: {search_query}")
            return False
        
        # 5. Забираем постер и видео из последних сообщений
        poster = None
        video = None
        movie_text = None
        
        async for msg in client.get_chat_history(bot_name, limit=10):
            if msg.photo and not poster:
                poster = msg.photo.file_id
                LOGGER.info(f"🖼️ Найден постер")
            if msg.video and not video:
                video = msg.video.file_id
                LOGGER.info(f"🎬 Найдено видео")
            if msg.text and "IMDb" in msg.text and not movie_text:
                movie_text = msg.text
        
        # 6. Извлекаем данные о фильме
        movie_data = await extract_movie(movie_text or target_msg.text)
        if not movie_data.get("title_ru"):
            LOGGER.warning(f"⚠️ Не удалось извлечь название фильма")
            return False
        
        # 7. Проверяем, есть ли уже такой фильм
        if movie_exists(movie_data["title_ru"]):
            LOGGER.info(f"⏭️ {movie_data['title_ru']} уже есть в базе")
            return True
        
        # 8. Сохраняем в базу
        movie_data["poster_file_id"] = poster
        movie_data["video_file_id"] = video
        movie_data["source_bot"] = bot_name
        save_movie(movie_data)
        
        # 9. Отправляем в канал
        if poster:
            await client.send_photo(
                chat_id=TARGET_CHANNEL,
                photo=poster,
                caption=(
                    f"🎬 *{movie_data.get('title_ru')} / {movie_data.get('title_en')}* ({movie_data.get('year')})\n"
                    f"⭐ IMDb: {movie_data.get('imdb_rating', 'N/A')}/10\n"
                    f"🆔 {movie_data.get('imdb_id')}"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        if video:
            await client.send_video(chat_id=TARGET_CHANNEL, video=video, caption="🎬 Видео")
        
        LOGGER.info(f"✅ Украден: {movie_data['title_ru']}")
        return True
        
    except Exception as e:
        LOGGER.error(f"❌ Ошибка при краже {search_query}: {e}")
        return False

# ===== КОМАНДЫ =====

@Client.on_message(filters.command("steal_bot", prefixes="."))
async def cmd_steal_bot(client: Client, msg: Message):
    """
    .steal_bot Название_фильма - крадёт один фильм
    .steal_bot - крадёт список фильмов из списка
    """
    init_db()
    args = msg.text.split(maxsplit=1)
    
    if len(args) > 1:
        # Крадём конкретный фильм
        query = args[1]
        await msg.reply(f"🎯 Краду: {query}...")
        success = await steal_from_bot(client, TARGET_BOT, query)
        if success:
            await msg.reply(f"✅ Фильм украден!")
        else:
            await msg.reply(f"❌ Не удалось украсть: {query}")
    else:
        # Крадём список фильмов
        movies_list = [
            "Человек-паук",
            "Железный человек", 
            "Тор",
            "Капитан Америка",
            "Мстители",
            "Бэтмен",
            "Супермен",
            "Форсаж",
            "Терминатор",
            "Матрица",
            "Властелин колец",
            "Гарри Поттер",
            "Пираты Карибского моря",
            "Трансформеры",
            "Джон Уик",
            "Дэдпул",
            "Логан",
            "Веном",
            "Доктор Стрэндж",
            "Черная пантера"
        ]
        await msg.reply(f"🎯 Начинаю кражу {len(movies_list)} фильмов...")
        
        stolen = 0
        for movie in movies_list:
            success = await steal_from_bot(client, TARGET_BOT, movie)
            if success:
                stolen += 1
            await asyncio.sleep(SEARCH_DELAY)  # Пауза между запросами
        
        await msg.reply(f"✅ Украдено фильмов: {stolen}/{len(movies_list)}")

@Client.on_message(filters.command("steal_status", prefixes="."))
async def cmd_steal_status(client: Client, msg: Message):
    count = get_movies_count()
    await msg.reply(f"📊 Украдено фильмов: {count}")

@Client.on_message(filters.command("steal_list", prefixes="."))
async def cmd_steal_list(client: Client, msg: Message):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT title_ru, year FROM movies ORDER BY created_at DESC LIMIT 20")
        rows = cur.fetchall()
    if not rows:
        await msg.reply("📭 В базе пока нет фильмов")
        return
    text = "📋 *Последние украденные фильмы:*\n" + "\n".join([f"• {r[0]} ({r[1]})" for r in rows])
    await msg.reply(text, parse_mode=ParseMode.MARKDOWN)

@Client.on_message(filters.command("steal_search", prefixes="."))
async def cmd_steal_search(client: Client, msg: Message):
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        await msg.reply("❌ .steal_search Название")
        return
    q = args[1]
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT title_ru, year, imdb_id FROM movies WHERE title_ru LIKE ? OR title_en LIKE ?", (f"%{q}%", f"%{q}%"))
        rows = cur.fetchall()
    if not rows:
        await msg.reply(f"😕 Не найдено: {q}")
        return
    text = f"🔍 *Найдено {len(rows)} фильмов:*\n" + "\n".join([f"• {r[0]} ({r[1]}) - `{r[2]}`" for r in rows])
    await msg.reply(text, parse_mode=ParseMode.MARKDOWN)
