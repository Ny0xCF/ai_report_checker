#!/bin/bash
set -e

APP_DIR="$HOME/ai_report_checker"

echo "===== Деплой приложения ====="

# Переходим в директорию приложения
cd "$APP_DIR" || { echo "Папка приложения не найдена: $APP_DIR"; exit 1; }

# Останавливаем приложение, если оно запущено
if pgrep -f 'python -m src.main' > /dev/null; then
    echo "Останавливаем текущее приложение..."
    pkill -f 'python -m src.main'
else
    echo "Приложение не запущено, продолжаем..."
fi

# Обновляем код из main
echo "Обновляем репозиторий..."
git fetch origin
git reset --hard origin/main

# Устанавливаем зависимости
echo "Устанавливаем зависимости..."
pip install -r requirements.txt --upgrade

# Запускаем приложение
echo "Запускаем приложение..."
nohup python -m src.main &

echo "===== Деплой завершен ====="
