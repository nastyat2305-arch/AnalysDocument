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

    def analyze_pair(self, ref_chunk: str, doc_chunk: str) -> Dict:
        """Отправляет пару фрагментов в LLM для анализа."""
        prompt = (
            f"Ты — эксперт по нормативным документам. Сравни фрагмент эталона и фрагмент документа.\n"
            f"ЭТАЛОН: \"{ref_chunk[:400]}\"\n"
            f"ДОКУМЕНТ: \"{doc_chunk[:400]}\"\n\n"
            f"Найди:\n"
            f"1. Логические противоречия (противоположные числа, условия, требования).\n"
            f"2. Смысловые разрывы (важные детали эталона, отсутствующие или искажённые в документе).\n"
            f"Верни ТОЛЬКО валидный JSON формата:\n"
            f"{{\n  \"logical_contradictions\": [{{\"ref\": \"...\", \"doc\": \"...\", \"reason\": \"...\"}}],\n"
            f"  \"semantic_gaps\": [{{\"ref_req\": \"...\", \"missing_context\": \"...\"}}]\n"
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
            """Обрабатывает один чанк документа против всех релевантных чанков эталона."""
            if doc_embs.size == 0:
                return None
            
            top_k = find_top_k_matches(doc_embs[idx], ref_embs, k=3)
            if not top_k:
                return {"logical_contradictions": [], "semantic_gaps": []}
            
            # ИСПРАВЛЕНИЕ: Анализируем ВСЕ релевантные пары, а не только первую
            chunk_contras = []
            chunk_gaps = []
            
            for r_idx in top_k:
                res = self.analyze_pair(ref_chunks[r_idx], doc_chunks[idx])
                if "error" not in res:
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
