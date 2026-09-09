# 🤖 Moon-Userbot — Гайд по Юзерботу с ИИ

Готовый юзербот с ChatGPT/Gemini/Claude через OpenRouter. Отвечает в личке и по тегу в группах.

## Что внутри (модуль chatbot.py)

Я улучшил твой оригинальный модуль:

**Было:**
- 9 моделей, команды `.aistatus` `.aimodel`

**Стало (улучшенная версия):**
- ✅ 11 моделей по умолчанию + добавление любых
- ✅ Анти-спам 1.5 сек на юзера
- ✅ История диалога в ЛС (`.aihistory` вкл/выкл, `.aiclear` очистка)
- ✅ Прямой запрос `.ai привет как дела` — отвечает от твоего аккаунта
- ✅ Защита от инъекций и от раскрытия промпта
- ✅ Чистка ссылок, разбивка длинных ответов, typing-индикатор
- ✅ Более стабильные заголовки для OpenRouter
- ✅ Команды редактируют сообщение (не спамят)

### Команды юзербота

| Команда | Что делает |
|---|---|
| `.aistatus` | Статус: ключ, модель, тест запроса |
| `.aimodel` | Список моделей |
| `.aimodel 2` | Выбрать модель по номеру |
| `.aimodel add openai/gpt-4o` | Добавить модель |
| `.aimodel del 3` | Удалить модель |
| `.aimodel reset` | Сброс на дефолт |
| `.ai <текст>` | Спросить ИИ напрямую (от твоего имени) |
| `.aihistory` | Вкл/выкл историю в ЛС |
| `.aiclear` | Очистить историю |

### Как отвечает

- **В личке:** на любое сообщение (кроме команд с префиксом `.`)
- **В группах:** только когда тегнули `@твой_ник` или ответили на сообщение юзербота
- Игнорит ботов и свои сообщения

## Установка — 3 способа

### 1. Локально (самый простой)

```bash
git clone https://github.com/твой_форк/Moon-Userbot
cd Moon-Userbot
pip install -r requirements.txt

# 1. Получи API_ID и API_HASH на https://my.telegram.org
# 2. Получи STRINGSESSION: python string_gen.py
# 3. Получи AI_KEY на https://openrouter.ai/keys

cp .env.dist .env
nano .env
# Заполни:
# API_ID=...
# API_HASH=...
# STRINGSESSION=...
# AI_KEY=sk-or-v1-...
# AI_MODEL=google/gemini-2.0-flash-001
# OWNER_ID=твой_id
# DATABASE_TYPE=sqlite
# DATABASE_NAME=moon.db

python main.py
```

### 2. Railway / Render / Koyeb (24/7)

1. Форкни репо
2. На Railway нажми New Project → Deploy from GitHub
3. Добавь Variables:
   ```
   API_ID=...
   API_HASH=...
   STRINGSESSION=...
   AI_KEY=sk-or-v1-...
   AI_BASE_URL=https://openrouter.ai/api/v1
   AI_MODEL=google/gemini-2.0-flash-001
   OWNER_ID=...
   DATABASE_TYPE=sqlite
   DATABASE_NAME=moon.db
   ```
4. Deploy → в логах должно быть `Userbot started!`

### 3. Termux (Android)

```bash
bash termux-install.sh
# вводи API_ID, HASH, STRINGSESSION когда спросит
```

## Где взять ключи

1. **API_ID / API_HASH:** https://my.telegram.org → API development tools
2. **STRINGSESSION:** 
   ```bash
   python string_gen.py
   # введи API_ID и API_HASH, потом код из Telegram
   # строку кинет в Saved Messages
   ```
3. **AI_KEY (OpenRouter):** https://openrouter.ai/keys → Create Key
   - Пополни баланс на $5-10, модели Gemini Flash стоят копейки
   - Бесплатные модели: `google/gemini-2.0-flash-001:free` и т.д.
4. **OWNER_ID:** напиши @userinfobot в Telegram

## Настройка моделей

По умолчанию стоят быстрые и дешевые:

```
google/gemini-2.0-flash-001
openai/gpt-4o-mini
meta-llama/llama-4-scout
```

Хочешь Claude или GPT-4o — добавь:

```
.aimodel add anthropic/claude-3.5-sonnet
.aimodel add openai/gpt-4o
.aimodel 5
```

Список всех моделей: https://openrouter.ai/models

## Частые проблемы

**`AI_KEY не задан`**
→ Проверь .env, рестартни `python main.py`

**Тестовый запрос падает 401**
→ Неверный AI_KEY

**429 Too Many Requests**
→ Кончились лимиты на OpenRouter, пополни баланс или смени модель на :free

**Юзербот не отвечает в группе**
→ Тегни его @username, или ответь на его сообщение

**Хочу чтобы не отвечал в некоторых чатах**
→ Добавлю в след. версии blacklist, пока можешь отключить модуль: переименуй `chatbot.py` в `chatbot.py.bak` и рестарт

## Безопасность

- Юзербот работает от твоего аккаунта — Telegram может ограничить за спам
- Не ставь маленький COOLDOWN (сейчас 1.5с — оптимально)
- Не давай STRINGSESSION никому
- Промпт защищен от раскрытия

## Что дальше?

Могу добавить:
- `.aiban` / `.aiunban` — запретить юзерам/чатам
- `.aiprompt` — менять характер бота из Telegram
- Авто-реакции, переводчик, суммаризация чатов
- Веб-панель для управления (уже есть `/` на порту)

Скажи что нужно — допилю.
