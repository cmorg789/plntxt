"""Embedding service using M2V_base_glove via model2vec."""

import logging
from functools import lru_cache

from model2vec import StaticModel

logger = logging.getLogger(__name__)

MODEL_NAME = "minishlab/M2V_base_glove"
EMBEDDING_DIM = 256


@lru_cache(maxsize=1)
def _get_model() -> StaticModel:
    logger.info("Loading embedding model %s", MODEL_NAME)
    return StaticModel.from_pretrained(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns list of 256-d float vectors."""
    model = _get_model()
    embeddings = model.encode(texts, normalize=True)
    return embeddings.tolist()


def embed_text(text: str) -> list[float]:
    """Embed a single text. Returns a 256-d float vector."""
    return embed_texts([text])[0]


def embed_query(query: str) -> list[float]:
    """Embed a search query. Returns a 256-d float vector."""
    return embed_text(query)
