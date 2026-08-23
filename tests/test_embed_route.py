"""Tests for POST /api/v1/embed."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.main import app

    return TestClient(app)


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
