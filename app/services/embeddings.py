"""Embedding service using nomic-embed-text-v1.5 via sentence-transformers."""

import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
# Matryoshka truncation — 256d is a good balance of quality vs storage
EMBEDDING_DIM = 256


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    logger.info("Loading embedding model %s", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    return model


def embed_texts(texts: list[str], prefix: str = "search_document: ") -> list[list[float]]:
    """Embed a batch of texts. Returns list of 256-d float vectors.

    Nomic requires a task prefix:
      - "search_document: " for content being stored/indexed
      - "search_query: " for queries at search time
    """
    model = _get_model()
    prefixed = [f"{prefix}{t}" for t in texts]
    embeddings = model.encode(prefixed, normalize_embeddings=True)
    # Truncate to Matryoshka dimension and re-normalize
    truncated = embeddings[:, :EMBEDDING_DIM]
    norms = np.linalg.norm(truncated, axis=1, keepdims=True)
    norms[norms == 0] = 1
    truncated = truncated / norms
    return truncated.tolist()


def embed_text(text: str, prefix: str = "search_document: ") -> list[float]:
    """Embed a single text. Returns a 256-d float vector."""
    return embed_texts([text], prefix=prefix)[0]


def embed_query(query: str) -> list[float]:
    """Embed a search query. Returns a 256-d float vector."""
    return embed_text(query, prefix="search_query: ")
