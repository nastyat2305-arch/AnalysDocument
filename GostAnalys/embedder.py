import os
import pickle
import threading
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class EmbeddingEngine:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_dir: str = "./cache"):
        self.model = SentenceTransformer(model_name)
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    @classmethod
    def get_instance(cls) -> 'EmbeddingEngine':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _cache_path(self, doc_id: str) -> str:
        safe = doc_id.replace(' ', '_').replace('/', '_')
        return os.path.join(self.cache_dir, f"emb_{safe}.pkl")

    def embed_chunks(self, chunks: list, doc_id: str = None) -> np.ndarray:
        """Принимает list[Dict] или list[str], извлекает текст для эмбеддинга."""
        if not chunks:
            return np.array([])

        # Нормализация: если чанки — Dict, берём поле 'text'
        texts = [c["text"] if isinstance(c, dict) else c for c in chunks]

        if doc_id and os.path.exists(self._cache_path(doc_id)):
            with open(self._cache_path(doc_id), 'rb') as f:
                return np.array(pickle.load(f))

        with self._lock:
            embs = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)

        if doc_id:
            with open(self._cache_path(doc_id), 'wb') as f:
                pickle.dump(embs.tolist(), f)
        return embs



def find_top_k_matches(query_emb: np.ndarray, corpus_embs: np.ndarray, k: int = 3) -> list:
    """Возвращает индексы k наиболее похожих блоков из эталона."""
    if query_emb.size == 0 or corpus_embs.size == 0:
        return []
    sims = cosine_similarity(query_emb.reshape(1, -1), corpus_embs)[0]
    return [int(i) for i in np.argsort(sims)[::-1][:k] if sims[i] > 0.35]
