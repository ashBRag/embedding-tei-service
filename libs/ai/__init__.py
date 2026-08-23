"""TEI-backed embeddings client.

Self-contained: no dependency on any other libs/* package.
"""

from libs.ai.embeddings import EmbeddingsSettings, TeiEmbeddings, build_embeddings

__all__ = ["EmbeddingsSettings", "TeiEmbeddings", "build_embeddings"]
