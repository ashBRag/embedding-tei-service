"""Reusable embeddings client for a HuggingFace Text Embeddings Inference (TEI) server.

Generic and reusable: `build_embeddings` takes an `EmbeddingsSettings` value
object instead of importing any project's settings class, so it can be
reused as-is in another project.

Calls a TEI server (https://github.com/huggingface/text-embeddings-inference)
over its `/embed` HTTP endpoint - no local model weights, no torch/
sentence-transformers dependency in this service. TEI is expected to run as
its own container (e.g. alongside Postgres/Redis on the shared network);
point `base_url` at it.

Usage:

    from libs.ai import EmbeddingsSettings, build_embeddings

    embeddings = build_embeddings(EmbeddingsSettings(base_url="http://tei:80"))

    vector = embeddings.embed_query("What is pgvector?")
    vectors = embeddings.embed_documents(["doc one text", "doc two text"])

    # async (used internally by libs.ai.vectorstore's async PGVector calls)
    vector = await embeddings.aembed_query("What is pgvector?")
"""

from dataclasses import dataclass

import httpx
from langchain_core.embeddings import Embeddings


@dataclass(frozen=True)
class EmbeddingsSettings:
    """Where to reach the TEI server, and request tuning.

    A plain value object (not a pydantic BaseSettings) so libs/ai has zero
    dependency on any particular settings/config library - the caller reads
    these values from wherever it likes and passes them in.
    """

    base_url: str  # e.g. "http://tei:80" (the TEI container's address)
    timeout: float = 30.0


class TeiEmbeddings(Embeddings):
    """LangChain Embeddings implementation backed by a TEI server's `/embed` endpoint.

    Implements both the sync and async methods natively (rather than relying
    on Embeddings' default async-via-thread-pool fallback), since this
    codebase is async-first and TEI is reached over the network either way.
    """

    def __init__(self, settings: EmbeddingsSettings):
        """Store settings; HTTP clients are created lazily on first use."""
        self._settings = settings
        self._client = httpx.Client(base_url=settings.base_url, timeout=settings.timeout)
        self._async_client = httpx.AsyncClient(base_url=settings.base_url, timeout=settings.timeout)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents via TEI's `/embed` endpoint."""
        response = self._client.post("/embed", json={"inputs": texts})
        response.raise_for_status()
        return response.json()

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string via TEI's `/embed` endpoint."""
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async: embed a batch of documents via TEI's `/embed` endpoint."""
        response = await self._async_client.post("/embed", json={"inputs": texts})
        response.raise_for_status()
        return response.json()

    async def aembed_query(self, text: str) -> list[float]:
        """Async: embed a single query string via TEI's `/embed` endpoint."""
        results = await self.aembed_documents([text])
        return results[0]

    async def health_check(self) -> bool:
        """Return True if TEI's `/health` endpoint responds successfully, False on any error.

        Used by `/health` so it never raises - a TEI outage should degrade
        the health response, not crash the health endpoint itself.
        """
        try:
            response = await self._async_client.get("/health")
            return response.status_code == 200
        except Exception:
            return False


def build_embeddings(settings: EmbeddingsSettings) -> TeiEmbeddings:
    """Build an Embeddings client that calls a TEI server over HTTP.

    Args:
        settings: TEI server URL + request timeout.

    Returns:
        TeiEmbeddings: a langchain_core.embeddings.Embeddings - usable
        anywhere LangChain expects an embeddings model, including
        `libs.ai.vectorstore.build_vector_store`.
    """
    return TeiEmbeddings(settings)
