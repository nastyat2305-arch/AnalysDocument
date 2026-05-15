import re
from typing import List, Dict

# Словарь доменов для пищевых ГОСТ (расширяемый)
FOOD_DOMAINS = {
    "microbiology": ["микрофлора", "КМАФАнМ", "БГКП", "патоген", "сальмонелл", "листерия"],
    "chemical": ["кислотное число", "перекисное число", "свинец", "кадмий", "ртуть", "мышьяк", "пестицид"],
    "physical": ["влажность", "плотность", "температура", "размер частиц", "вязкость"],
    "organizational": ["ХАССП", "декларация", "сертификат", "утилизация", "спецодежда", "обучение персонала"],
    "packaging": ["упаковка", "маркировка", "срок годности", "условия хранения", "транспорт"],
    "raw_materials": ["сырьё", "жир", "масло", "стеариновая кислота", "молоко", "мясо"]
}


def _extract_domain_hints(text: str) -> List[str]:
    """Определяет доменные метки по ключевым словам."""
    text_lower = text.lower()
    return [domain for domain, keywords in FOOD_DOMAINS.items()
            if any(kw.lower() in text_lower for kw in keywords)]


def _extract_numerical_context(text: str) -> List[Dict]:
    """Извлекает числовые показатели с единицами и условиями."""
    # Паттерн: число + (опционально) единица + (опционально) условие в скобках
    pattern = r'(\d+[.,]?\d*)\s*([а-яёA-Za-z/²³]+)?(?:\s*\(([^)]+)\))?'
    matches = re.finditer(pattern, text)
    return [
        {"value": float(m.group(1).replace(',', '.')),
         "unit": m.group(2).strip() if m.group(2) else None,
         "condition": m.group(3).strip() if m.group(3) else None,
         "raw": m.group(0)}
        for m in matches if m.group(1)
    ]


def split_into_chunks(text: str, chunk_size: int = 800, overlap: int = 100) -> List[Dict]:
    """Возвращает список Dict с ключами: 'text', 'meta', 'numerics'."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks = []
    current = ""

    for p in paragraphs:
        if len(current) + len(p) > chunk_size and current:
            chunk_meta = {
                "type": _extract_domain_hints(current),
                "has_numbers": bool(_extract_numerical_context(current)),
                "char_span": {"start": text.find(current), "end": text.find(current) + len(current)}
            }
            chunks.append({
                "text": current.strip(),
                "meta": chunk_meta,
                "numerics": _extract_numerical_context(current)
            })
            # overlap с сохранением контекста
            overlap_text = " ".join(current.split()[-overlap // 4:]) if len(current.split()) > overlap // 4 else ""
            current = overlap_text + " " + p
        else:
            current += (" " if current else "") + p

    if current.strip():
        chunk_meta = {
            "type": _extract_domain_hints(current),
            "has_numbers": bool(_extract_numerical_context(current)),
            "char_span": {"start": text.find(current), "end": text.find(current) + len(current)}
        }
        chunks.append({
            "text": current.strip(),
            "meta": chunk_meta,
            "numerics": _extract_numerical_context(current)
        })

    return [c for c in chunks if len(c["text"]) > 50]
