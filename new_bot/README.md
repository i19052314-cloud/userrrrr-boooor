# Такой же бот как в Moon-Userbot chatbot.py — но как обычный Telegram Bot

Это **standalone версия** твоего юзербота. Работает через BotFather, не нужен API_ID/HASH и STRINGSESSION.

## Что умеет (1-в-1 как оригинал)

- ✅ Отвечает в личке на любые сообщения
- ✅ В группах отвечает только когда его упомянули `@бот` или ответили на его сообщение
- ✅ Использует OpenRouter / любой OpenAI-совместимый API
- ✅ Команда `/aistatus` — проверка ключа, модели, тестовый запрос
- ✅ Команда `/aimodel` — управление моделями:
  - `/aimodel` или `/aimodel list` — список
  - `/aimodel 2` — выбрать по номеру
  - `/aimodel add openai/gpt-4o` — добавить
  - `/aimodel del 3` — удалить
  - `/aimodel reset` — сброс на дефолт
- ✅ Защита промпта: не раскрывает как сделан, игнорирует инъекции, не отвечает на вопросы про создание бота
- ✅ Чистит ссылки, typing-индикатор, обработка ошибок
- ✅ SQLite база для моделей (как в оригинале)

## Быстрый старт

1. Создай бота у @BotFather, получи токен
2. Получи ключ OpenRouter на https://openrouter.ai/
3. Установи зависимости:

```bash
pip install -r requirements.txt
```

4. Скопируй `.env.example` в `.env` и заполни:

```bash
cp .env.example .env
nano .env
```

5. Запусти:

```bash
python bot.py
```

## Переменные окружения

| Переменная | Описание | Пример |
|---|---|---|
| BOT_TOKEN | Токен от @BotFather | 123456:AAH... |
| AI_BASE_URL | URL API | https://openrouter.ai/api/v1 |
| AI_KEY | Ключ API | sk-or-v1-... |
| AI_MODEL | Модель по умолчанию | google/gemini-2.0-flash-001 |
| OWNER_ID | Твой Telegram ID | 123456789 |
| OWNER_NAME | Имя владельца | Иван |

## Деплой

### Railway / Render / Koyeb

Просто залей папку `new_bot` как отдельный сервис, добавь переменные окружения.

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

## Отличия от юзербота

| Юзербот (оригинал) | Этот бот |
|---|---|
| Работает от твоего аккаунта | Работает как отдельный бот |
| Нужен API_ID, API_HASH, STRINGSESSION | Нужен только BOT_TOKEN |
| Команды `.aistatus` | Команды `/aistatus` |
| Может читать все чаты | Только там где его добавили |
| Риск бана аккаунта | Безопасно |

## Модели по умолчанию

```
- google/gemini-2.0-flash-001
- google/gemini-1.5-flash-8b
- openai/gpt-4o-mini
- meta-llama/llama-4-scout
- mistralai/mistral-7b-instruct
- MiniMaxAI/MiniMax-M2.7
- MiniMaxAI/MiniMax-M3
- stealth/ox-alpha
- z-ai/glm-5.3-flash
```

Добавляй любые с OpenRouter через `/aimodel add`.

## Хочешь юзербот версию?

Она уже есть в репозитории: `modules/custom_modules/chatbot.py`

Запуск юзербота:

```bash
# Заполни .env в корне репо (API_ID, API_HASH, STRINGSESSION, AI_KEY...)
python main.py
```

---

Сделано на основе Moon-Userbot chatbot модуля.
