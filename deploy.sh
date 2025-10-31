#!/bin/bash
set -e

APP_DIR="$HOME/ai_report_checker"
LOCK_FILE="$APP_DIR/.deploy.lock"

echo "===== Деплой приложения ====="

# Защита от одновременного запуска деплоя
if [ -f "$LOCK_FILE" ]; then
    echo "Деплой уже запущен! Выходим..."
    exit 1
fi
touch "$LOCK_FILE"

cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Переходим в директорию приложения
cd "$APP_DIR" || { echo "Папка приложения не найдена: $APP_DIR"; exit 1; }

# Останавливаем приложение, если оно запущено
if pgrep -f 'python3 -m src.main' > /dev/null; then
    echo "Приложение было запущено, останавливаем..."
    pkill -f 'python3 -m src.main' || echo "Не удалось остановить приложение, возможно оно уже завершилось"
else
    echo "Приложение не запущено, продолжаем..."
fi

# Обновляем код из main
echo "Обновляем репозиторий..."
git fetch origin || { echo "Ошибка при git fetch"; exit 1; }
git reset --hard origin/main || { echo "Ошибка при git reset"; exit 1; }

# Устанавливаем зависимости
echo "Устанавливаем зависимости..."
pip install -r requirements.txt --upgrade || { echo "Ошибка при установке зависимостей"; exit 1; }

# Запускаем приложение в фоне и отвязываем от SSH
echo "Запускаем приложение..."
nohup python3 -m src.main > /dev/null 2>&1 &
disown

# Ждём 1 секунду, чтобы процесс стартовал
sleep 1

# Проверяем, запущен ли процесс
if ! pgrep -f 'python3 -m src.main' > /dev/null; then
    echo "Ошибка: приложение не запустилось!"
    exit 1
fi

echo "===== Деплой завершен ====="
