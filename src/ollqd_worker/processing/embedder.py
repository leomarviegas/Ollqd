"""Ollama embedding client — wraps /api/embed endpoint."""

import logging
from typing import Optional

import httpx

from ..errors import EmbeddingError
from ..models import Chunk

log = logging.getLogger("ollqd.embedder")


class OllamaEmbedder:
    """Generate embeddings via Ollama's /api/embed endpoint."""

    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout)
        self._dim: Optional[int] = None

    def _embed_request(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"]
        except httpx.HTTPError as e:
            raise EmbeddingError(f"Ollama embed request failed: {e}") from e
        except (KeyError, ValueError) as e:
            raise EmbeddingError(f"Invalid Ollama embed response: {e}") from e

    def get_dimension(self) -> int:
        if self._dim is None:
            vecs = self._embed_request(["dimension probe"])
            self._dim = len(vecs[0])
            log.info("Embedding dimension: %d (model: %s)", self._dim, self.model)
        return self._dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._embed_request(texts)

    def embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
        texts = []
        for c in chunks:
            prefix = f"File: {c.file_path} | Language: {c.language} | Lines {c.start_line}-{c.end_line}\n\n"
            texts.append(prefix + c.content)
        return self._embed_request(texts)

    def embed_query(self, query: str) -> list[float]:
        vecs = self._embed_request([query])
        return vecs[0]

    def close(self):
        self._client.close()
