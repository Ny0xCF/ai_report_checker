import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"

# Формат сообщений
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ------------------- Конфигурация -------------------

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),  # Вывод в консоль
        logging.FileHandler(LOG_FILE, encoding="utf-8"),  # Запись в файл
    ],
)


def get_logger(name: str) -> logging.Logger:
    """Возвращает сконфигурированный логгер с единым форматом"""
    return logging.getLogger(name)
