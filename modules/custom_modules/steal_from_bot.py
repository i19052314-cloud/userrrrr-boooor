"""
Модуль для Moon-Userbot: кража фильмов с автоматическим поиском и нажатием кнопок
by @loveaideep
"""

import asyncio
import sqlite3
import re
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

LOGGER = logging.getLogger(__name__)
DB_PATH = "movies.db"

# ===== КОНФИГ =====
TARGET_BOT = "NitokinMedia23Bot"  # 👈 ИМЯ БОТА, У КОТОРОГО ВОРУЕМ
TARGET_CHANNEL = "your_channel"  # 👈 ТВОЙ КАНАЛ

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

# ===== ПАРСИНГ =====
def extract_movie(text):
    data = {}
    if not text:
        return data
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

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
async def steal_from_bot(client, bot_name, search_query):
    LOGGER.info(f"🎯 Ищу фильм: {search_query}")
    stolen_count = 0
    
    try:
        # 1. Отправляем запрос
        await client.send_message(bot_name, search_query)
        await asyncio.sleep(4)
        
        # 2. Получаем ответы бота
        responses = []
        async for m in client.get_chat_history(bot_name, limit=15):
            if m.from_user and m.from_user.is_bot:
                responses.append(m)
        
        if not responses:
            LOGGER.warning("❌ Нет ответа от бота")
            return 0
        
        # 3. Ищем сообщение с кнопками
        target_msg = None
        for msg in responses:
            if msg.reply_markup and msg.text and ("кнопк" in msg.text.lower() or "выбери" in msg.text.lower()):
                target_msg = msg
                LOGGER.info(f"🔍 Найдено сообщение с кнопками")
                break
        
        if not target_msg:
            LOGGER.warning("⚠️ Не найдено сообщение с кнопками")
            return 0
        
        # 4. Нажимаем на ВСЕ кнопки по очереди
        if target_msg.reply_markup:
            for row in target_msg.reply_markup.inline_keyboard:
                for btn in row:
                    LOGGER.info(f"🔘 Нажимаю кнопку: {btn.text}")
                    
                    try:
                        await client.request_callback_answer(
                            chat_id=bot_name,
                            message_id=target_msg.id,
                            callback_data=btn.callback_data
                        )
                        await asyncio.sleep(4)
                        
                        # 5. Забираем постер и видео
                        poster = None
                        video = None
                        movie_text = None
                        
                        async for m in client.get_chat_history(bot_name, limit=10):
                            if m.photo and not poster:
                                poster = m.photo.file_id
                            if m.video and not video:
                                video = m.video.file_id
                            if m.text and "IMDb" in m.text and not movie_text:
                                movie_text = m.text
                        
                        # 6. Извлекаем данные
                        movie_data = extract_movie(movie_text)
                        if not movie_data.get("title_ru"):
                            # Пробуем парсить из текста кнопки
                            if " / " in btn.text:
                                parts = btn.text.split(" / ")
                                movie_data["title_ru"] = parts[0].strip()
                                movie_data["title_en"] = parts[1].strip() if len(parts) > 1 else ""
                            else:
                                movie_data["title_ru"] = btn.text.strip()
                        
                        if not movie_data.get("title_ru"):
                            LOGGER.warning("⚠️ Не удалось извлечь название")
                            continue
                        
                        # 7. Проверяем дубликат
                        if movie_exists(movie_data["title_ru"]):
                            LOGGER.info(f"⏭️ {movie_data['title_ru']} уже есть")
                            continue
                        
                        # 8. Сохраняем
                        movie_data["poster_file_id"] = poster
                        movie_data["video_file_id"] = video
                        movie_data["source_bot"] = bot_name
                        save_movie(movie_data)
                        stolen_count += 1
                        
                        # 9. Пересылаем в канал
                        if poster:
                            await client.send_photo(
                                chat_id=TARGET_CHANNEL,
                                photo=poster,
                                caption=(
                                    f"🎬 *{movie_data.get('title_ru')} / {movie_data.get('title_en')}* ({movie_data.get('year', 'N/A')})\n"
                                    f"⭐ IMDb: {movie_data.get('imdb_rating', 'N/A')}/10\n"
                                    f"🆔 {movie_data.get('imdb_id', 'N/A')}"
                                ),
                                parse_mode=ParseMode.MARKDOWN
                            )
                        if video:
                            await client.send_video(chat_id=TARGET_CHANNEL, video=video, caption="🎬 Видео")
                        
                        LOGGER.info(f"✅ Украден: {movie_data['title_ru']}")
                        
                    except Exception as e:
                        LOGGER.error(f"❌ Ошибка при нажатии кнопки {btn.text}: {e}")
                        continue
        
        return stolen_count
        
    except Exception as e:
        LOGGER.error(f"❌ Ошибка: {e}")
        return 0

# ===== КОМАНДЫ =====

@Client.on_message(filters.command("steal_bot", prefixes="."))
async def cmd_steal_bot(client: Client, msg: Message):
    init_db()
    args = msg.text.split(maxsplit=1)
    
    if len(args) > 1:
        query = args[1]
        await msg.reply(f"🎯 Ищу: {query}...")
        stolen = await steal_from_bot(client, TARGET_BOT, query)
        if stolen > 0:
            await msg.reply(f"✅ Украдено фильмов: {stolen}")
        else:
            await msg.reply(f"❌ Не удалось украсть: {query}")
    else:
        movies = ["Человек-паук", "Железный человек", "Тор", "Мстители", "Бэтмен", "Супермен", "Форсаж"]
        await msg.reply(f"🎯 Начинаю кражу {len(movies)} фильмов...")
        total = 0
        for m in movies:
            stolen = await steal_from_bot(client, TARGET_BOT, m)
            total += stolen
            await asyncio.sleep(5)
        await msg.reply(f"✅ Всего украдено: {total}")

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
        await msg.reply("📭 Пусто")
        return
    text = "📋 *Последние фильмы:*\n" + "\n".join([f"• {r[0]} ({r[1]})" for r in rows])
    await msg.reply(text, parse_mode=ParseMode.MARKDOWN)
