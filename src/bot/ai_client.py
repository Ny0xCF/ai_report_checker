import asyncio
from dataclasses import dataclass
from typing import List
from pathlib import Path

import openai
from dotenv import load_dotenv
import os

from src.bot import utils


@dataclass
class Recommendation:
    criterion: str
    issues: List[str]


@dataclass
class ReportCheckResult:
    recommendations: List[Recommendation]
    corrected_report: str


class AIClient:
    #  Базовый системный промпт с инструкцией формата
    BASE_RULES_PROMPT = """
    Роль и задача
    -------------
    Роль:
    Ты - внутренний редактор тел полицейских отчетов для ролевой игры
    
    Задача:
    Выполнять предварительную проверку тела отчета по заданному чек-листу и предлагать улучшения и исправленный вариант
    
    Основные принципы проверки
    ---------------------------
    - Используй русский язык (если не указано иное)
    - Все роли указываются на русском языке (офицер, подозреваемый, свидетель и т.д.)
    - Отчет должен быть написан в официальном стиле, как реальные полицейские отчеты (но не перегружен формализмами)
    - Не используй слова "наряд", "милиция" и любые другие термины, свойственные СНГ полиции - только термины американской полиции
    - Тон изложения нейтральный и объективный. Без эмоций, оценочных суждений и разговорных фраз
    - Структура текста логична и хронологична
    - Используй прошедшее время и третье лицо
    - Не добавляй вымышленные детали. Разрешено переформулировать для читаемости и связности
    - Не оформляй текст (никакого жирного, курсивного и т.п.)
    - Можно разделять текст на абзацы, но без оформления или выносов
    - Все временные отметки, номера ордеров, патрулей, улицы, имена и данные сохраняются без изменений
    - Рекомендации в блоке с исправленной версии отчета вставляй через скобки [], не надо заполнять их выдуманными данными
    - Не придумывай рекомендации, которых нет в критериях проверки
    
    Формат ответа
    -------------
    В ответе нужно предоставить два блока:
    1. Список рекомендаций - только конкретные замечания по улучшению отчета (в точности по критериям)
    2. Исправленный вариант отчета - с учетом рекомендаций, без оформления и вымышленных данных
    
    В ответе отдавай результат СТРОГО В ФОРМАТЕ JSON СО СЛЕДУЮЩЕЙ СТРУКТУРОЙ:
    
    {
      "recommendations": [
        {
          "criterion": "Название критерия проверки (например, Стиль изложения)",
          "issues": [
            "Конкретная проблема по этому критерию",
            "Еще одна проблема"
          ]
        },
        ...
      ],
      "corrected_report": "Исправленный текст отчета с учетом рекомендаций.
      Для мест, которые требуют уточнения или корректировки, используй скобки [ ] без выдуманных данных"
    }
    
    - В массиве "recommendations" перечисляй только конкретные замечания по критериям проверки
    - Все рекомендации и исправления должны строго соответствовать критериям проверки
    - Поле "corrected_report" содержит готовый к исправлению отчет с вставленными скобками [ ] там, где требуется исправление или уточнение
    - Не добавляй лишнего текста вне JSON
    """.strip()

    def __init__(
            self,
            env_path: Path,
            prompt_path: Path,
            model_name: str = "tngtech/deepseek-r1t2-chimera:free",
            max_concurrent: int = 10,
    ):
        # Загрузка переменных окружения
        load_dotenv(dotenv_path=env_path)
        api_key = os.getenv("OPENROUTER_TOKEN")
        if not api_key:
            raise ValueError("OPENROUTER_TOKEN не найден в .env")

        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        # Загружаем промт
        if not prompt_path.exists():
            raise FileNotFoundError(f"Файл промта не найден: {prompt_path}")
        self.role_prompt = prompt_path.read_text(encoding="utf-8") + f"\n\n---\n\n{self.BASE_RULES_PROMPT}"

        self.model_name = model_name
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def _sync_query(self, messages: List[dict]):
        """Синхронный запрос к API OpenRouter"""
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
        )

    async def query(self, user_message: str) -> ReportCheckResult:
        """Асинхронный запрос к модели с автоматическим преобразованием в DTO"""
        async with self.semaphore:
            try:
                response = await asyncio.to_thread(
                    self._sync_query,
                    [
                        {"role": "system", "content": self.role_prompt},
                        {"role": "user", "content": user_message},
                    ],
                )
                data = utils.extract_json(response.choices[0].message.content)
                recommendations = [Recommendation(**r) for r in data.get("recommendations", [])]
                corrected = data.get("corrected_report", "")
                return ReportCheckResult(recommendations, corrected)
            except Exception as e:
                raise RuntimeError(f"Не удалось выполнить запрос: {e}")
