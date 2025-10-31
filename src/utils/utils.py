import json
import re


def extract_json(raw_text: str) -> dict:
    """Извлекает JSON-объект из текста, даже если вокруг есть текст"""
    match = re.search(r"\{.*}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("Не удалось найти JSON в переданном тексте")
    json_str = match.group(0)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Ошибка парсинга JSON: {e}\n"
                         f"Сырой текст:\n"
                         f"{raw_text[:500]}")
