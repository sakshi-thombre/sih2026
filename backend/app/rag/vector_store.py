"""Vector storage.

`VectorStore` is the swap point for Person D's future PostgreSQL/
pgvector-backed implementation — the service/retriever/API layers only
ever depend on this interface, never on `LocalVectorStore` directly.

`LocalVectorStore` is a local prototype: embeddings are persisted as a
plain numpy `.npy` array and chunk metadata as JSON, deliberately not
pickle, so the on-disk format stays inspectable and safe to load. Not
suitable for concurrent multi-process access or very large corpora —
adequate for a single-process prototype.
"""

import json
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from app.rag.base import DocumentChunk


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        """Store chunks alongside their embedding vectors."""

    @abstractmethod
    def search(self, query_embedding: list[float], top_k: int) -> list[DocumentChunk]:
        """Return the top_k chunks most similar to the query embedding, scored."""

    @abstractmethod
    def delete(self, document_id: str) -> None:
        """Remove all chunks belonging to a document."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored chunks."""


class LocalVectorStore(VectorStore):
    def __init__(self, storage_dir: str) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._vectors_path = self._dir / "vectors.npy"
        self._metadata_path = self._dir / "metadata.json"
        self._lock = threading.Lock()
        self._vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self._metadata: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._metadata_path.exists() and self._vectors_path.exists():
            with self._metadata_path.open("r", encoding="utf-8") as f:
                self._metadata = json.load(f)
            self._vectors = np.load(self._vectors_path, allow_pickle=False)

    def _save(self) -> None:
        tmp_metadata_path = self._metadata_path.with_suffix(".json.tmp")
        with tmp_metadata_path.open("w", encoding="utf-8") as f:
            json.dump(self._metadata, f)
        tmp_metadata_path.replace(self._metadata_path)

        tmp_vectors_path = self._dir / "vectors.npy.tmp"
        with tmp_vectors_path.open("wb") as f:
            np.save(f, self._vectors, allow_pickle=False)
        tmp_vectors_path.replace(self._vectors_path)

    def add(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must be the same length")
        if not chunks:
            return

        new_vectors = np.array(embeddings, dtype=np.float32)
        with self._lock:
            if self._vectors.shape[0] == 0:
                self._vectors = new_vectors
            else:
                self._vectors = np.vstack([self._vectors, new_vectors])

            self._metadata.extend(
                {
                    "document_id": chunk.document_id,
                    "filename": chunk.filename,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            )
            self._save()

    def search(self, query_embedding: list[float], top_k: int) -> list[DocumentChunk]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        with self._lock:
            if self._vectors.shape[0] == 0:
                return []

            query = np.array(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query)
            if query_norm == 0:
                return []

            vector_norms = np.linalg.norm(self._vectors, axis=1)
            denominators = vector_norms * query_norm
            denominators[denominators == 0] = 1e-10
            similarities = (self._vectors @ query) / denominators

            k = min(top_k, similarities.shape[0])
            top_indices = np.argsort(-similarities)[:k]

            return [
                DocumentChunk(
                    document_id=self._metadata[idx]["document_id"],
                    filename=self._metadata[idx]["filename"],
                    chunk_id=self._metadata[idx]["chunk_id"],
                    text=self._metadata[idx]["text"],
                    score=float(similarities[idx]),
                    page_number=self._metadata[idx].get("page_number"),
                    chunk_index=self._metadata[idx].get("chunk_index"),
                )
                for idx in top_indices
            ]

    def delete(self, document_id: str) -> None:
        with self._lock:
            keep_indices = [i for i, meta in enumerate(self._metadata) if meta["document_id"] != document_id]
            if len(keep_indices) == len(self._metadata):
                return

            self._metadata = [self._metadata[i] for i in keep_indices]
            self._vectors = (
                self._vectors[keep_indices]
                if keep_indices
                else np.zeros((0, self._vectors.shape[1] if self._vectors.ndim == 2 else 0), dtype=np.float32)
            )
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._metadata = []
            self._vectors = np.zeros((0, 0), dtype=np.float32)
            self._save()
