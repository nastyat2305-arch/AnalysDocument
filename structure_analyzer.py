import json
from openai import OpenAI

STRUCTURE_TEMPLATES = {
    "ТУ": ["область применения", "технические требования", "правила приемки", "методы контроля", "транспортирование и хранение", "гарантии изготовителя"],
    "ТК": ["назначение", "область применения", "сырье и материалы", "оборудование", "последовательность операций", "контроль качества", "требования безопасности"],
    "ТИ": ["назначение", "требования к сырью", "технологический процесс", "контроль качества", "упаковка и хранение"],
    "МУ": ["область применения", "аппаратура и реактивы", "подготовка к анализу", "проведение анализа", "обработка результатов", "контроль точности"]
}

def analyze_structure_ai(client: OpenAI, model: str, text: str, doc_type: str) -> list:
    """AI проверяет структуру документа по типу."""
    template = STRUCTURE_TEMPLATES.get(doc_type, STRUCTURE_TEMPLATES.get("МУ", []))
    prompt = (
        f"Извлеки из документа фактическую структуру (заголовки/разделы). "
        f"Сравни с обязательной структурой для типа {doc_type}: {', '.join(template)}.\n"
        f"Верни JSON массив отсутствующих или нарушенных разделов: "
        f"[{{\"section\": \"название\", \"status\": \"missing/altered\", \"details\": \"пояснение\"}}]"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"Текст документа (первые 3000 символов):\n{text[:3000]}\n\n{prompt}"}],
            temperature=0.1,
            max_tokens=300
        )
        cleaned = resp.choices[0].message.content.strip()
        return json.loads(cleaned)
    except:
        return [{"section": "Ошибка анализа структуры", "status": "unknown", "details": "AI не смог обработать структуру"}]