import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import dotenv

dotenv.load_dotenv()

LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL").upper(), logging.DEBUG)
LOG_DIR = Path(sys.path[0]).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=LOG_LEVEL,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        # logging.StreamHandler(sys.stdout),  # Вывод в консоль
        RotatingFileHandler(
            LOG_DIR / "bot.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,  # храним 3 файла максимум
            encoding="utf-8"
        ),  # Запись в файл
    ],
)


def get_logger(name: str) -> logging.Logger:
    """Возвращает сконфигурированный логгер с единым форматом"""
    return logging.getLogger(name)
