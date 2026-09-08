#!/bin/bash
echo "🌙 Moon-Userbot + AI ChatBot — быстрый старт"
echo ""

if [ ! -f .env ]; then
  echo "📝 Создаю .env из .env.dist..."
  cp .env.dist .env
  echo "⚠️  Заполни .env! Открываю..."
  echo "Нужны: API_ID, API_HASH, STRINGSESSION, AI_KEY"
  echo ""
  echo "Где взять:"
  echo "  API_ID/HASH: https://my.telegram.org"
  echo "  STRINGSESSION: python string_gen.py"
  echo "  AI_KEY: https://openrouter.ai/keys"
  echo ""
  read -p "Нажми Enter чтобы открыть .env..."
  nano .env 2>/dev/null || vi .env
fi

echo "📦 Устанавливаю зависимости..."
pip install -r requirements.txt

echo ""
echo "🚀 Запускаю юзербота..."
python main.py
