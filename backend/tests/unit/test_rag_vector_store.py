"""Unit tests for LocalVectorStore. Uses a temp directory per test —
no shared state, no external services."""

from app.rag.base import DocumentChunk
from app.rag.vector_store import LocalVectorStore


def make_chunk(document_id: str, chunk_index: int, text: str, filename: str = "doc.txt") -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        filename=filename,
        chunk_id=f"{document_id}:{chunk_index}",
        text=text,
        score=0.0,
        page_number=None,
        chunk_index=chunk_index,
    )


def test_add_and_search_returns_most_similar_first(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    chunks = [
        make_chunk("doc-1", 0, "pressure relief valve"),
        make_chunk("doc-1", 1, "completely unrelated text about cats"),
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    store.add(chunks, embeddings)

    results = store.search([1.0, 0.0, 0.0], top_k=2)

    assert len(results) == 2
    assert results[0].chunk_id == "doc-1:0"
    assert results[0].score > results[1].score


def test_search_respects_top_k(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    chunks = [make_chunk("doc-1", i, f"chunk {i}") for i in range(5)]
    embeddings = [[float(i), 0.0, 0.0] for i in range(5)]
    store.add(chunks, embeddings)

    results = store.search([1.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2


def test_search_on_empty_store_returns_empty_list(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    results = store.search([1.0, 0.0, 0.0], top_k=5)
    assert results == []


def test_search_preserves_metadata(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    chunk = make_chunk("doc-1", 3, "safety procedure text", filename="sop.pdf")
    store.add([chunk], [[1.0, 0.0]])

    results = store.search([1.0, 0.0], top_k=1)

    assert results[0].document_id == "doc-1"
    assert results[0].filename == "sop.pdf"
    assert results[0].chunk_index == 3
    assert results[0].text == "safety procedure text"


def test_delete_removes_only_matching_document(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    store.add([make_chunk("doc-1", 0, "a")], [[1.0, 0.0]])
    store.add([make_chunk("doc-2", 0, "b")], [[0.0, 1.0]])

    store.delete("doc-1")

    results = store.search([1.0, 0.0], top_k=10)
    assert all(r.document_id != "doc-1" for r in results)
    assert any(r.document_id == "doc-2" for r in results)


def test_clear_removes_everything(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    store.add([make_chunk("doc-1", 0, "a")], [[1.0, 0.0]])

    store.clear()

    assert store.search([1.0, 0.0], top_k=10) == []


def test_persistence_survives_new_instance(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    store.add([make_chunk("doc-1", 0, "persisted chunk")], [[1.0, 0.0]])

    reloaded_store = LocalVectorStore(str(tmp_path))
    results = reloaded_store.search([1.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].text == "persisted chunk"


def test_add_rejects_mismatched_lengths(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    try:
        store.add([make_chunk("doc-1", 0, "a")], [[1.0, 0.0], [0.0, 1.0]])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_storage_files_are_not_pickle(tmp_path) -> None:
    store = LocalVectorStore(str(tmp_path))
    store.add([make_chunk("doc-1", 0, "a")], [[1.0, 0.0]])

    metadata_path = tmp_path / "metadata.json"
    vectors_path = tmp_path / "vectors.npy"
    assert metadata_path.exists()
    assert vectors_path.exists()
    # metadata.json must be plain JSON, not a pickle stream.
    import json

    with metadata_path.open() as f:
        data = json.load(f)
    assert data[0]["document_id"] == "doc-1"
