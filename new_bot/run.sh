#!/bin/bash
# Запуск бота
if [ ! -f .env ]; then
  echo "❌ Нет .env файла! Скопируй .env.example в .env и заполни"
  echo "cp .env.example .env"
  exit 1
fi
pip install -r requirements.txt
python bot.py
