"""Reusable embeddings clients for HuggingFace TEI and Voyage AI.

Generic and reusable: both `build_embeddings` and `build_voyage_embeddings`
take plain settings value objects instead of importing any project's
settings class, so they can be reused as-is in another project.

TeiEmbeddings calls a TEI server (https://github.com/huggingface/text-embeddings-inference)
over its `/embed` HTTP endpoint - no local model weights, no torch/
sentence-transformers dependency in this service. TEI is expected to run as
its own container (e.g. alongside Postgres/Redis on the shared network);
point `base_url` at it.

VoyageEmbeddings calls Voyage AI's hosted `/v1/embeddings` HTTP API
(https://docs.voyageai.com/reference/embeddings-api) using an API key.

Usage:

    from libs.ai import EmbeddingsSettings, build_embeddings

    embeddings = build_embeddings(EmbeddingsSettings(base_url="http://tei:80"))

    vector = embeddings.embed_query("What is pgvector?")
    vectors = embeddings.embed_documents(["doc one text", "doc two text"])

    # async (used internally by libs.ai.vectorstore's async PGVector calls)
    vector = await embeddings.aembed_query("What is pgvector?")

    from libs.ai import VoyageEmbeddingsSettings, build_voyage_embeddings

    voyage = build_voyage_embeddings(
        VoyageEmbeddingsSettings(api_key="...", model="voyage-3.5-lite")
    )
    vectors = await voyage.aembed_documents(["doc one", "doc two"], input_type="document")
"""

from dataclasses import dataclass
from typing import Literal

import httpx
from langchain_core.embeddings import Embeddings

VoyageInputType = Literal["query", "document"] | None


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


@dataclass(frozen=True)
class VoyageEmbeddingsSettings:
    """Voyage AI API credentials and request tuning.

    A plain value object (not a pydantic BaseSettings) so libs/ai has zero
    dependency on any particular settings/config library - the caller reads
    these values from wherever it likes and passes them in.
    """

    api_key: str
    model: str
    timeout: float = 30.0
    base_url: str = "https://api.voyageai.com/v1"


class VoyageEmbeddings(Embeddings):
    """LangChain Embeddings implementation backed by Voyage AI's `/embeddings` endpoint.

    Voyage's API distinguishes `input_type="query"` vs `"document"` for
    better retrieval quality - the base `Embeddings` interface has no such
    parameter, so it's exposed here as an extra keyword argument rather than
    an override (callers that only need the plain LangChain interface can
    ignore it; `input_type` then defaults to None, Voyage's "no hint" mode).
    """

    def __init__(self, settings: VoyageEmbeddingsSettings):
        """Store settings; HTTP clients are created lazily on first use."""
        self._settings = settings
        headers = {"Authorization": f"Bearer {settings.api_key}"}
        self._client = httpx.Client(base_url=settings.base_url, timeout=settings.timeout, headers=headers)
        self._async_client = httpx.AsyncClient(base_url=settings.base_url, timeout=settings.timeout, headers=headers)

    def _payload(self, texts: list[str], input_type: VoyageInputType) -> dict:
        payload: dict = {"input": texts, "model": self._settings.model}
        if input_type is not None:
            payload["input_type"] = input_type
        return payload

    @staticmethod
    def _parse(response: httpx.Response) -> list[list[float]]:
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]

    def embed_documents(self, texts: list[str], input_type: VoyageInputType = "document") -> list[list[float]]:
        """Embed a batch of documents via Voyage's `/embeddings` endpoint."""
        response = self._client.post("/embeddings", json=self._payload(texts, input_type))
        return self._parse(response)

    def embed_query(self, text: str, input_type: VoyageInputType = "query") -> list[float]:
        """Embed a single query string via Voyage's `/embeddings` endpoint."""
        return self.embed_documents([text], input_type=input_type)[0]

    async def aembed_documents(self, texts: list[str], input_type: VoyageInputType = "document") -> list[list[float]]:
        """Async: embed a batch of documents via Voyage's `/embeddings` endpoint."""
        response = await self._async_client.post("/embeddings", json=self._payload(texts, input_type))
        return self._parse(response)

    async def aembed_query(self, text: str, input_type: VoyageInputType = "query") -> list[float]:
        """Async: embed a single query string via Voyage's `/embeddings` endpoint."""
        results = await self.aembed_documents([text], input_type=input_type)
        return results[0]

    async def health_check(self) -> bool:
        """Return True if a minimal Voyage embed call succeeds, False on any error.

        Voyage has no dedicated health endpoint, so this issues the
        cheapest possible real call. Used by `/health` so it never raises -
        a Voyage outage should degrade the health response, not crash the
        health endpoint itself.
        """
        try:
            response = await self._async_client.post("/embeddings", json=self._payload(["ok"], "query"))
            return response.status_code == 200
        except Exception:
            return False


def build_voyage_embeddings(settings: VoyageEmbeddingsSettings) -> VoyageEmbeddings:
    """Build an Embeddings client that calls Voyage AI's hosted API.

    Args:
        settings: Voyage API key, model, and request tuning.

    Returns:
        VoyageEmbeddings: a langchain_core.embeddings.Embeddings - usable
        anywhere LangChain expects an embeddings model.
    """
    return VoyageEmbeddings(settings)
