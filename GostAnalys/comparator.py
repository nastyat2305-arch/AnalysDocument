import json
import time
import threading
import logging
from typing import List, Dict
from openai import OpenAI
from pydantic import BaseModel, Field
import numpy as np

logger = logging.getLogger(__name__)


class AIAnalysisResult(BaseModel):
    logical_contradictions: List[Dict[str, str]] = Field(..., description="Логические противоречия")
    semantic_gaps: List[Dict[str, str]] = Field(..., description="Смысловые разрывы")


CROSS_DOMAIN_BLACKLIST = {
    ("microbiology", "packaging"),  # микробиология ≠ упаковка
    ("chemical", "organizational"),  # хим.показатели ≠ ХАССП
    ("raw_materials", "organizational"),  # сырьё ≠ спецодежда
}


def _domains_compatible(ref_meta: dict, doc_meta: dict) -> bool:
    """Проверяет, есть ли пересечение доменов или оба — 'general'."""
    ref_types = set(ref_meta.get("type", []))
    doc_types = set(doc_meta.get("type", []))

    # Если есть пересечение — разрешаем
    if ref_types & doc_types:
        return True

    # Если хотя бы один чанк — организационный, а другой — технический,
    # проверяем чёрный список
    for r_type in ref_types:
        for d_type in doc_types:
            if (r_type, d_type) in CROSS_DOMAIN_BLACKLIST or (d_type, r_type) in CROSS_DOMAIN_BLACKLIST:
                return False
    return True  # Пограничные случаи пропускаем для LLM


def _numerical_context_match(ref_nums: List[Dict], doc_nums: List[Dict], tolerance: float = 0.1) -> Dict:
    """Сравнивает числовые показатели с учётом единиц и условий."""
    if not ref_nums or not doc_nums:
        return {"match": True, "details": "no_numbers"}  # Нет чисел — не блокируем

    matches = []
    for rn in ref_nums:
        for dn in doc_nums:
            # Сравниваем только если единицы совпадают или одна отсутствует
            if rn["unit"] and dn["unit"] and rn["unit"].lower() != dn["unit"].lower():
                continue  # Разные единицы — пропуск
            # Сравниваем значения с допуском
            if abs(rn["value"] - dn["value"]) / max(rn["value"], 1e-6) <= tolerance:
                matches.append({"ref": rn["raw"], "doc": dn["raw"], "diff": abs(rn["value"] - dn["value"])})

    return {
        "match": bool(matches),
        "details": matches if matches else "value_mismatch"
    }
class AIComparator:
    def __init__(self, api_key: str, base_url: str, model: str, max_retries: int = 3):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_retries = max_retries
        self.rate_limit_lock = threading.Semaphore(5)  # Ограничение параллельных запросов к API

    def _parse_json_response(self, response_text: str) -> Dict:
        """Очищает ответ от markdown и парсит JSON."""
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())

    def analyze_pair(self, ref_chunk: str, doc_chunk: str, numeric_context: str = None) -> Dict:
        numeric_hint = f"\n⚠️ КОНТЕКСТ ЧИСЕЛ: {numeric_context}" if numeric_context else ""

        prompt = (
            f"Ты — эксперт по нормативным документам в пищевой промышленности. "
            f"Сравни фрагмент эталона и фрагмент документа.\n\n"
            f"📋 ЭТАЛОН:\n{ref_chunk[:500]}\n\n"
            f"📄 ДОКУМЕНТ:\n{doc_chunk[:500]}{numeric_hint}\n\n"
            f"🎯 ЗАДАЧА:\n"
            f"1. Определи, релевантны ли эти фрагменты для сравнения (is_relevant: bool).\n"
            f"   — НЕ релевантны, если: разные домены (микробиология ↔ упаковка), "
            f"   организационные требования ↔ технические параметры без связи, "
            f"   числа с разными единицами без контекста.\n"
            f"2. Если is_relevant=true, найди:\n"
            f"   • Логические противоречия (противоположные числа, условия, требования)\n"
            f"   • Смысловые разрывы (важные детали эталона, отсутствующие в документе)\n"
            f"3. Если is_relevant=false, укажи причину в relevant_reason.\n\n"
            f"📦 ВЕРНИ ТОЛЬКО валидный JSON:\n"
            f"{{\n"
            f'  "is_relevant": true,\n'
            f'  "relevant_reason": "краткое обоснование (если false)",\n'
            f'  "logical_contradictions": [{{"ref": "...", "doc": "...", "reason": "..."}}],\n'
            f'  "semantic_gaps": [{{"ref_req": "...", "missing_context": "..."}}]\n'
            f"}}"
        )

        for attempt in range(self.max_retries):
            try:
                with self.rate_limit_lock:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "system", "content": "Ответ строго в JSON. Никаких пояснений."},
                                  {"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=500
                    )
                return self._parse_json_response(resp.choices[0].message.content)
            except Exception as e:
                logger.warning(f"Попытка {attempt + 1}/{self.max_retries} не удалась: {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"Ошибка анализа пары: {e}")
                    return {"logical_contradictions": [], "semantic_gaps": [], "error": str(e)}
                time.sleep(2 ** attempt)

    def batch_analyze(self, ref_chunks: list, doc_chunks: list, ref_embs: np.ndarray, doc_embs: np.ndarray) -> Dict:
        """Параллельно анализирует все релевантные пары."""
        import numpy as np
        from embedder import find_top_k_matches
        import concurrent.futures

        all_contras = []
        all_gaps = []

        def process_chunk(idx):
            if doc_embs.size == 0:
                return None

            top_k = find_top_k_matches(doc_embs[idx], ref_embs, k=5)  # Увеличиваем k для отбора
            if not top_k:
                return {"logical_contradictions": [], "semantic_gaps": []}

            chunk_contras = []
            chunk_gaps = []

            for r_idx in top_k:
                # === НОВАЯ ЛОГИКА ПРЕ-ФИЛЬТРАЦИИ ===
                ref_chunk = ref_chunks[r_idx]
                doc_chunk = doc_chunks[idx]

                # Извлекаем метаданные (поддержка старых str-чанков)
                ref_meta = ref_chunk.get("meta", {}) if isinstance(ref_chunk, dict) else {}
                doc_meta = doc_chunk.get("meta", {}) if isinstance(doc_chunk, dict) else {}
                ref_nums = ref_chunk.get("numerics", []) if isinstance(ref_chunk, dict) else []
                doc_nums = doc_chunk.get("numerics", []) if isinstance(doc_chunk, dict) else []

                # 1. Проверка доменной совместимости
                if not _domains_compatible(ref_meta, doc_meta):
                    continue  # Пропускаем заведомо нерелевантную пару

                # 2. Проверка числового контекста (если есть числа)
                num_check = _numerical_context_match(ref_nums, doc_nums)
                if not num_check["match"] and num_check["details"] != "no_numbers":
                    # Не блокируем полностью, но добавляем контекст для LLM
                    numeric_warning = f"⚠️ Числа: {num_check['details']}"
                else:
                    numeric_warning = None

                # === ОТПРАВКА В LLM С ДОП. КОНТЕКСТОМ ===
                res = self.analyze_pair(
                    ref_chunk["text"] if isinstance(ref_chunk, dict) else ref_chunk,
                    doc_chunk["text"] if isinstance(doc_chunk, dict) else doc_chunk,
                    numeric_context=numeric_warning  # Новый параметр
                )

                # Фильтруем результаты по флагу is_relevant
                if "error" not in res and res.get("is_relevant", True):
                    chunk_contras.extend(res.get("logical_contradictions", []))
                    chunk_gaps.extend(res.get("semantic_gaps", []))

            return {
                "logical_contradictions": chunk_contras,
                "semantic_gaps": chunk_gaps
            }
            
            

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(process_chunk, range(len(doc_chunks))))

        for r in results:
            if r:
                all_contras.extend(r.get("logical_contradictions", []))
                all_gaps.extend(r.get("semantic_gaps", []))

        return {"contradictions": all_contras, "gaps": all_gaps}
