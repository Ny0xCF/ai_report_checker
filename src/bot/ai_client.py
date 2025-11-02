import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import httpx
import openai
from dotenv import load_dotenv

from src.utils import logger
from src.utils import utils
from src.utils.config_loader import PROMPTS_BASE_DIR

logger = logger.get_logger("ai_client")


@dataclass
class Recommendation:
    criterion: str
    issues: List[str]


@dataclass
class ReportCheckResult:
    recommendations: List[Recommendation]
    corrected_report: str


class AIClient:
    BASE_RULES_PROMPT = (PROMPTS_BASE_DIR / "base_rules.txt").read_text(encoding="utf-8").strip()

    def __init__(
            self,
            env_path: Path,
            prompt_path: Path,
            model_name: str = "tngtech/deepseek-r1t2-chimera:free",
            max_concurrent: int = 10,
    ):
        # Загружаем токен
        load_dotenv(dotenv_path=env_path)
        api_key = os.getenv("OPENROUTER_TOKEN")
        if not api_key:
            raise ValueError("OPENROUTER_TOKEN не найден в .env")

        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            http_client=httpx.Client()
        )

        # Загружаем промпт
        if not prompt_path.exists():
            raise FileNotFoundError(f"Файл промта не найден: {prompt_path}")

        self.role_prompt = (
                prompt_path.read_text(encoding="utf-8").strip()
                + f"\n\n---\n\n{self.BASE_RULES_PROMPT}"
        )

        self.model_name = model_name
        self.semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(f"AIClient инициализирован: модель={model_name}, max_concurrent={max_concurrent}")

    def _sync_query(self, messages: List[dict]):
        """Синхронный запрос к API OpenRouter"""
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
        )

    async def query(self, user_message: str, history: Optional[List[dict]] = None) -> ReportCheckResult:
        """
        Асинхронный запрос к модели с логированием и поддержкой контекста (истории диалога)
        """
        async with self.semaphore:
            logger.debug(f"Отправка запроса к модели ({self.model_name})")

            # Формируем историю сообщений
            messages = [{"role": "system", "content": self.role_prompt}]
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": user_message})

            logger.debug(f"Отправляется {len(messages)} сообщений в модель")

            try:
                response = await asyncio.to_thread(self._sync_query, messages)
                content = response.choices[0].message.content
                logger.debug("Ответ от модели получен")
                logger.debug(f"Сырой ответ: {content}")

                data = utils.extract_json(content)
                recommendations = [Recommendation(**r) for r in data.get("recommendations", [])]
                corrected = data.get("corrected_report", "")
                return ReportCheckResult(recommendations, corrected)

            except Exception as e:
                raise RuntimeError(f"Не удалось выполнить запрос: {e}")
