"""
Модуль для кражи фильмов у чужого бота
Для Moon-Userbot by @loveaideep
"""

import asyncio
import sqlite3
import re
import logging
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== КОНФИГ =====
TARGET_BOT = "NitokinMoviesBot"  # ЧУЖОЙ БОТ (ЗАМЕНИ!)
TARGET_CHANNEL = "your_channel"  # ТВОЙ КАНАЛ (ЗАМЕНИ!)
DB_PATH = "movies.db"

# ===== БАЗА ДАННЫХ =====
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_ru TEXT,
                title_en TEXT,
                year TEXT,
                imdb_id TEXT,
                imdb_rating TEXT,
                description TEXT,
                tags TEXT,
                size TEXT,
                poster_file_id TEXT,
                video_file_id TEXT,
                download_link TEXT,
                source_bot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def movie_exists(title: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM movies WHERE title_ru LIKE ? OR title_en LIKE ?", (f"%{title}%", f"%{title}%"))
        return cursor.fetchone() is not None

def save_movie(data: dict):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO movies (
                title_ru, title_en, year, imdb_id, imdb_rating,
                description, tags, size, poster_file_id,
                video_file_id, download_link, source_bot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("title_ru"),
            data.get("title_en"),
            data.get("year"),
            data.get("imdb_id"),
            data.get("imdb_rating"),
            data.get("description"),
            data.get("tags"),
            data.get("size"),
            data.get("poster_file_id"),
            data.get("video_file_id"),
            data.get("download_link"),
            data.get("source_bot")
        ))
        conn.commit()
        logger.info(f"💾 Сохранён: {data.get('title_ru')}")

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С БОТОМ =====
async def send_message_to_bot(app: Client, bot_username: str, text: str):
    try:
        msg = await app.send_message(bot_username, text)
        await asyncio.sleep(2)
        return msg
    except Exception as e:
        logger.error(f"Ошибка отправки боту: {e}")
        return None

async def get_bot_response(app: Client, bot_username: str, limit: int = 5):
    try:
        responses = []
        async for msg in app.get_chat_history(bot_username, limit=limit):
            if msg.from_user and msg.from_user.is_bot:
                responses.append(msg)
        return responses
    except Exception as e:
        logger.error(f"Ошибка получения ответа: {e}")
        return []

async def click_button(app: Client, bot_username: str, callback_data: str, message_id: int):
    try:
        await app.request_callback_answer(
            chat_id=bot_username,
            message_id=message_id,
            callback_data=callback_data
        )
        await asyncio.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Ошибка нажатия кнопки: {e}")
        return False

async def extract_movie_data(text: str) -> dict:
    data = {}
    match = re.search(r'^(.*?)\s*/\s*(.*?)\s*\((\d{4})\)', text)
    if match:
        data["title_ru"] = match.group(1).strip()
        data["title_en"] = match.group(2).strip()
        data["year"] = match.group(3)
    imdb_match = re.search(r'imdb\.com/title/(tt\d+)', text)
    if imdb_match:
        data["imdb_id"] = imdb_match.group(1)
    rating_match = re.search(r'(\d+\.\d+)/10\s*⭐', text)
    if rating_match:
        data["imdb_rating"] = rating_match.group(1)
    size_match = re.search(r'Размер.*?:\s*(.*?)(?:\n|$)', text)
    if size_match:
        data["size"] = size_match.group(1).strip()
    tags_match = re.search(r'Tags:\s*(#\S+(?:\s*#\S+)*)', text)
    if tags_match:
        data["tags"] = tags_match.group(1).strip()
    download_match = re.search(r'Download.*?\((https://t\.me/[^\)]+)\)', text)
    if download_match:
        data["download_link"] = download_match.group(1)
    return data

async def steal_movie(app: Client, bot_username: str, movie_title: str):
    logger.info(f"🎯 Начинаю кражу: {movie_title}")
    
    response = await send_message_to_bot(app, bot_username, movie_title)
    if not response:
        logger.error(f"❌ Нет ответа от бота по запросу: {movie_title}")
        return
    
    if not response.reply_markup:
        logger.warning(f"⚠️ Нет кнопок для: {movie_title}")
        return
    
    for row in response.reply_markup.inline_keyboard:
        for button in row:
            if button.text and movie_title.lower() in button.text.lower():
                logger.info(f"🔘 Нажимаю кнопку: {button.text}")
                await click_button(app, bot_username, button.callback_data, response.id)
                await asyncio.sleep(3)
                
                movie_data = None
                poster_id = None
                video_id = None
                
                async for msg in app.get_chat_history(bot_username, limit=10):
                    if msg.from_user.is_bot:
                        if msg.text and "IMDb" in msg.text:
                            movie_data = await extract_movie_data(msg.text)
                            if movie_data and movie_data.get("title_ru"):
                                movie_data["source_bot"] = bot_username
                                break
                        if msg.photo and not poster_id:
                            poster_id = msg.photo.file_id
                        if msg.video and not video_id:
                            video_id = msg.video.file_id
                
                if movie_data and movie_data.get("title_ru"):
                    if not movie_exists(movie_data["title_ru"]):
                        movie_data["poster_file_id"] = poster_id
                        movie_data["video_file_id"] = video_id
                        save_movie(movie_data)
                        await forward_to_channel(app, movie_data, poster_id, video_id)
                        logger.info(f"✅ Украден фильм: {movie_data['title_ru']}")
                    else:
                        logger.info(f"⏭️ Пропуск: {movie_data['title_ru']} уже есть")
                else:
                    logger.warning(f"⚠️ Не удалось извлечь данные для: {movie_title}")
                break

async def forward_to_channel(app: Client, data: dict, poster_id: str, video_id: str):
    try:
        caption = (
            f"🎬 *{data.get('title_ru', '')} / {data.get('title_en', '')}* ({data.get('year', '')})\n"
            f"⭐ IMDb: {data.get('imdb_rating', 'N/A')}/10\n"
            f"🏷️ {data.get('tags', '')}\n"
            f"📦 Размер: {data.get('size', 'N/A')}\n"
            f"🆔 IMDB: `{data.get('imdb_id', '')}`"
        )
        if poster_id:
            await app.send_photo(chat_id=TARGET_CHANNEL, photo=poster_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
        if video_id:
            await app.send_video(chat_id=TARGET_CHANNEL, video=video_id, caption="🎬 Видео")
        logger.info(f"📤 Переслано в канал: {data.get('title_ru')}")
    except Exception as e:
        logger.error(f"Ошибка пересылки: {e}")

# ===== РЕГИСТРАЦИЯ КОМАНД =====
@Client.on_message(filters.command("steal_bot", prefixes="."))
async def steal_from_bot(client: Client, message: Message):
    init_db()
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await message.reply(f"🎯 Краду фильм: {args[1]}")
        await steal_movie(client, TARGET_BOT, args[1])
        await message.reply("✅ Готово!")
    else:
        movies_list = [
            "Человек-паук", "Железный человек", "Тор", "Капитан Америка",
            "Мстители", "Бэтмен", "Супермен", "Форсаж", "Терминатор",
            "Матрица", "Властелин колец", "Гарри Поттер", "Пираты Карибского моря",
            "Трансформеры", "Джон Уик", "Дэдпул", "Логан", "Веном",
            "Доктор Стрэндж", "Черная пантера"
        ]
        await message.reply(f"🎯 Начинаю кражу {len(movies_list)} фильмов...")
        for movie in movies_list:
            await steal_movie(client, TARGET_BOT, movie)
            await asyncio.sleep(5)
        await message.reply("✅ Все фильмы украдены!")

@Client.on_message(filters.command("steal_status", prefixes="."))
async def steal_status(client: Client, message: Message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies")
        count = cursor.fetchone()[0]
        await message.reply(f"📊 Украдено фильмов: {count}")

@Client.on_message(filters.command("steal_list", prefixes="."))
async def steal_list(client: Client, message: Message):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title_ru, year FROM movies ORDER BY created_at DESC LIMIT 20")
        movies = cursor.fetchall()
        if not movies:
            await message.reply("📭 Фильмов пока нет")
            return
        text = "📋 *Последние украденные фильмы:*\n\n"
        for title, year in movies:
            text += f"• {title} ({year})\n"
        await message.reply(text, parse_mode=ParseMode.MARKDOWN)

@Client.on_message(filters.command("steal_search", prefixes="."))
async def steal_search(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("❌ Укажи название: .steal_search Человек-паук")
        return
    query = args[1]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title_ru, year, imdb_id FROM movies WHERE title_ru LIKE ? OR title_en LIKE ?", (f"%{query}%", f"%{query}%"))
        movies = cursor.fetchall()
        if not movies:
            await message.reply(f"😕 Не найдено: {query}")
            return
        text = f"🔍 *Найдено {len(movies)} фильмов:*\n\n"
        for title, year, imdb_id in movies:
            text += f"• {title} ({year}) - `{imdb_id}`\n"
        await message.reply(text, parse_mode=ParseMode.MARKDOWN)
