#!/bin/bash
# Запуск бота на Mac/Linux: подвійний клік (Mac) або ./start.command
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python не знайдено. Встанови його з https://www.python.org/downloads/ і запусти знову."
  read -r -p "Натисни Enter, щоб закрити..."
  exit 1
fi

if [ ! -f .venv/installed.ok ]; then
  echo "=== Перший запуск: встановлюю бота, це займе 2-5 хвилин ==="
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install --upgrade pip
  if ! .venv/bin/python -m pip install -r requirements.txt; then
    echo "Не вдалося встановити бібліотеки. Перевір інтернет і запусти ще раз."
    read -r -p "Натисни Enter, щоб закрити..."
    exit 1
  fi
  echo ok > .venv/installed.ok
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "=== Створено файл .env ==="
  echo "Впиши TELEGRAM_BOT_TOKEN і GEMINI_API_KEY, збережи файл і запусти start.command знову."
  open -e .env 2>/dev/null || ${EDITOR:-nano} .env
  read -r -p "Натисни Enter, щоб закрити..."
  exit 0
fi

echo "=== Бот запущений. Не закривай це вікно, поки користуєшся ботом ==="
echo "Щоб зупинити бота, натисни Ctrl+C."
.venv/bin/python -m bot.main
read -r -p "Бот зупинився. Натисни Enter, щоб закрити..."
