"""Lazy local embeddings with an offline deterministic fallback."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
from collections.abc import Sequence

from backend.config import settings

logger = logging.getLogger(__name__)
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")


class EmbeddingService:
    """Use BGE when available; keep ingestion/search usable without a model download."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", fallback_dim: int = 384):
        self.model_name = model_name
        self.fallback_dim = fallback_dim
        self._model = None
        self._model_failed = False
        self._lock = threading.Lock()

    @property
    def active_model(self) -> str:
        return self.model_name if self._model is not None else "hashing-char-ngram-v1"

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        with self._lock:
            model = self._load_model()
            if model is not None:
                try:
                    vectors = model.get_text_embedding_batch(list(texts))
                    return [list(map(float, vector)) for vector in vectors]
                except Exception as exc:
                    self._model_failed = True
                    logger.warning(
                        "BGE embedding failed; using deterministic fallback: %s", exc
                    )
        return [self._hash_embedding(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def _load_model(self):
        if self._model is not None or self._model_failed:
            return self._model
        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            self._model = HuggingFaceEmbedding(model_name=self.model_name, trust_remote_code=True)
        except Exception as exc:
            self._model_failed = True
            logger.warning("BGE model unavailable; using deterministic fallback: %s", exc)
        return self._model

    def _hash_embedding(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", " ", text.casefold()).strip()
        features = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]", normalized)
        features += [normalized[index : index + 2] for index in range(max(0, len(normalized) - 1))]
        vector = [0.0] * self.fallback_dim
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.fallback_dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


embedding_service = EmbeddingService(model_name=settings.RAG_EMBEDDING_MODEL)
