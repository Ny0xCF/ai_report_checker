import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.utils.config_loader import logger_config

LOG_DIR = Path(sys.path[0]).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logger_config.logging.level,
    format=logger_config.logging.format,
    datefmt=logger_config.logging.datefmt,
    handlers=[
        # logging.StreamHandler(sys.stdout),  # Вывод в консоль
        RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,  # храним 3 файла максимум
            encoding="utf-8"
        ),  # Запись в файл
    ],
)


def get_logger(name: str) -> logging.Logger:
    """Возвращает сконфигурированный логгер с единым форматом"""
    return logging.getLogger(name)
