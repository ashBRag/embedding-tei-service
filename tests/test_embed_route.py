"""Tests for POST /api/v1/embed."""

import time
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def _auth_headers() -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "test-user",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "scope": "",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.main import app

    return TestClient(app, headers=_auth_headers())


def _mock_tei_embed(monkeypatch: pytest.MonkeyPatch, vectors: list[list[float]]) -> None:
    monkeypatch.setattr(
        "app.integrations.tei.TeiEmbeddings.aembed_documents",
        AsyncMock(return_value=vectors),
    )


def test_embed_returns_one_vector_per_text(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    vector = [0.1] * settings.TEI_EMBEDDING_DIM
    _mock_tei_embed(monkeypatch, [vector, vector])

    response = client.post("/api/v1/embed", json={"texts": ["hello", "world"]})

    assert response.status_code == 200
    body = response.json()
    assert body["dimension"] == settings.TEI_EMBEDDING_DIM
    assert len(body["embeddings"]) == 2
    assert body["embeddings"][0] == vector


def test_embed_rejects_empty_texts_list(client: TestClient):
    response = client.post("/api/v1/embed", json={"texts": []})
    assert response.status_code == 422


def test_embed_rejects_oversized_text(client: TestClient):
    response = client.post("/api/v1/embed", json={"texts": ["x" * (settings.EMBED_MAX_TEXT_CHARS + 1)]})
    assert response.status_code == 422


def test_embed_returns_502_on_dimension_mismatch(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _mock_tei_embed(monkeypatch, [[0.1] * (settings.TEI_EMBEDDING_DIM - 1)])

    response = client.post("/api/v1/embed", json={"texts": ["hello"]})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_embedding_error"


def test_embed_rejects_unknown_provider(client: TestClient):
    response = client.post("/api/v1/embed", json={"texts": ["hello"], "provider": "does-not-exist"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_embedding_provider"


def test_embed_rejects_voyage_when_not_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Voyage is only registered if VOYAGE_API_KEY is set at startup - without it, requesting it is a 400, not a 502."""
    from app.main import embedding_providers

    assert "voyage" not in embedding_providers

    response = client.post("/api/v1/embed", json={"texts": ["hello"], "provider": "voyage"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_embedding_provider"


def test_embed_uses_voyage_when_registered(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.integrations.voyage import VoyageEmbeddingService
    from app.main import app, embedding_providers
    from libs.ai.embeddings import VoyageEmbeddings, VoyageEmbeddingsSettings

    vector = [0.2] * 1024
    voyage_client = VoyageEmbeddings(VoyageEmbeddingsSettings(api_key="test-key", model="voyage-3.5-lite"))
    monkeypatch.setattr(
        VoyageEmbeddings,
        "aembed_documents",
        AsyncMock(return_value=[vector]),
    )
    embedding_providers["voyage"] = VoyageEmbeddingService(voyage_client)
    try:
        with TestClient(app, headers=_auth_headers()) as scoped_client:
            response = scoped_client.post(
                "/api/v1/embed",
                json={"texts": ["hello"], "provider": "voyage", "input_type": "query"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["dimension"] == 1024
        assert body["embeddings"] == [vector]
    finally:
        del embedding_providers["voyage"]
