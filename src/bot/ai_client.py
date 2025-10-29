import os
import asyncio
import json
import re
from dataclasses import dataclass
from typing import List

import openai
from dotenv import load_dotenv

# ------------------- DTO -------------------
@dataclass
class Recommendation:
    criterion: str
    issues: List[str]

@dataclass
class ReportCheckResult:
    recommendations: List[Recommendation]
    corrected_report: str

# ------------------- Настройка -------------------
load_dotenv(dotenv_path="D:\\PyCharm\\ReportHelper\\src\\bot\\.env")
OPENROUTER_TOKEN = os.getenv("OPENROUTER_TOKEN")
if not OPENROUTER_TOKEN:
    raise ValueError("OPENROUTER_TOKEN не найден в src/bot/.env")

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_TOKEN
)

with open("D:\\PyCharm\\ReportHelper\\src\\prompts\\arrest_report.txt", "r", encoding="utf-8") as f:
    ROLE_PROMPT = f.read()

MODEL_NAME = "tngtech/deepseek-r1t2-chimera:free"  # Модель OpenRouter.ai

def extract_json(raw_text: str):
    # ищем первый открывающий { и последний закрывающий }
    match = re.search(r"\{.*}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("Не удалось найти JSON в ответе ИИ")
    json_str = match.group(0).replace("\n", "")
    return json.loads(json_str)

# ------------------- Синхронная функция -------------------
def sync_query(user_message: str):
    return client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": ROLE_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )

# ------------------- Семафор для ограничений -------------------
semaphore = asyncio.Semaphore(5)  # максимум 5 одновременных запросов

# ------------------- Асинхронный клиент -------------------
async def query_ai(user_message: str) -> ReportCheckResult:
    async with semaphore:
        try:
            response = await asyncio.to_thread(sync_query, user_message)
            # Преобразуем ответ ИИ из строки JSON в DTO
            data = extract_json(response.choices[0].message.content)
            recommendations = [Recommendation(**rec) for rec in data.get("recommendations", [])]
            corrected_report = data.get("corrected_report", "")
            return ReportCheckResult(recommendations=recommendations, corrected_report=corrected_report)
        except Exception as e:
            raise RuntimeError(f"Ошибка при запросе к OpenAI: {e}")

# ------------------- Тестовый запуск -------------------
async def main():
    test_report = "В 16:00 20.07.2025 дежурными офицерами станции Мишен-Роу были услышаны хлопки схожие с выстрелами малокалиберного оружия в свеверо-восточной стороне от станции у сухих каналов. В ходе пешего прибытия на место выстрелов, офицерами был замечен подозреваемый, некий Рентон Шаннон и свидетельница неизвестная малолетняя девушка, в ходе проведения задержания и полевого расследования, офицеры обнаружили за пазухой шорт подозреваемого Рентона пистолет модели SR40 и шесть патронов 9 миллиметров."
    result = await query_ai(test_report)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
