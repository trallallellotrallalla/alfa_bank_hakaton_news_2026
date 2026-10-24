"""Локальная модель эмбеддингов (fastembed / ONNX — без torch, образ меньше).

ВАЖНО для команды: запросы агента к поиску векторизуются этой же моделью
внутри модуля (search_events, search_analytics, подбор под клиента принимают текст),
поэтому самим считать эмбеддинги снаружи не нужно.
"""

import logging
import threading

import numpy as np
from fastembed import TextEmbedding

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str, dim: int, cache_dir: str | None = None):
        self.model_name = model_name
        self.dim = dim
        self.cache_dir = cache_dir
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()
        # e5-модели обучены с префиксами "query: " / "passage: "
        self._e5 = "e5" in model_name.lower()

    def _get(self) -> TextEmbedding:
        with self._lock:
            if self._model is None:
                log.info("загрузка модели эмбеддингов %s", self.model_name)
                self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
            return self._model

    def warmup(self) -> None:
        self.embed_passages(["прогрев"])

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prefix = "passage: " if self._e5 else ""
        return self._embed([prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self.embed_queries([text])[0]

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prefix = "query: " if self._e5 else ""
        return self._embed([prefix + t for t in texts])

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get()
        with self._lock:  # ONNX-сессия не гарантирует потокобезопасность
            vectors = list(model.embed(texts, batch_size=16))
        out = []
        for v in vectors:
            v = np.asarray(v, dtype=np.float32)
            if v.shape[0] != self.dim:
                raise ValueError(
                    f"модель {self.model_name} даёт размерность {v.shape[0]}, а EMBEDDING_DIM={self.dim}"
                )
            norm = np.linalg.norm(v)
            out.append((v / norm if norm else v).tolist())
        return out
