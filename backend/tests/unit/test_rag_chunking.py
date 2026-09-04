"""Unit tests for deterministic text chunking. Pure logic, no I/O."""

import pytest

from app.rag.chunking import chunk_document
from app.rag.loaders import ExtractedPage


def test_chunk_short_document_produces_single_chunk() -> None:
    pages = [ExtractedPage(page_number=1, text="short text")]
    chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    assert len(chunks) == 1
    assert chunks[0].text == "short text"
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1


def test_chunk_long_document_produces_multiple_chunks_with_overlap() -> None:
    text = "".join(f"{i:04d}" for i in range(500))  # 2000 chars
    pages = [ExtractedPage(page_number=1, text=text)]
    chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    assert len(chunks) > 1
    # Overlap: the tail of chunk N should reappear at the head of chunk N+1.
    overlap_text = chunks[0].text[-150:]
    assert chunks[1].text.startswith(overlap_text)


def test_chunk_indices_increment_sequentially_across_pages() -> None:
    pages = [
        ExtractedPage(page_number=1, text="a" * 1500),
        ExtractedPage(page_number=2, text="b" * 500),
    ]
    chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    indices = [chunk.chunk_index for chunk in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_preserves_page_number_per_chunk() -> None:
    pages = [
        ExtractedPage(page_number=1, text="a" * 1500),
        ExtractedPage(page_number=2, text="b" * 500),
    ]
    chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    page_1_chunks = [c for c in chunks if c.page_number == 1]
    page_2_chunks = [c for c in chunks if c.page_number == 2]
    assert len(page_1_chunks) >= 1
    assert len(page_2_chunks) == 1
    assert all("b" in c.text for c in page_2_chunks)


def test_chunk_skips_empty_pages() -> None:
    pages = [
        ExtractedPage(page_number=1, text=""),
        ExtractedPage(page_number=2, text="real content here"),
    ]
    chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    assert len(chunks) == 1
    assert chunks[0].page_number == 2


def test_chunk_document_is_deterministic() -> None:
    pages = [ExtractedPage(page_number=1, text="repeatable text " * 200)]

    first = chunk_document(pages, chunk_size=1000, chunk_overlap=150)
    second = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    assert [c.text for c in first] == [c.text for c in second]
    assert [c.chunk_index for c in first] == [c.chunk_index for c in second]


def test_chunk_no_page_number_preserved_as_none() -> None:
    pages = [ExtractedPage(page_number=None, text="txt/docx style content with no page")]
    chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=150)

    assert all(c.page_number is None for c in chunks)


def test_chunk_rejects_non_positive_chunk_size() -> None:
    pages = [ExtractedPage(page_number=1, text="text")]
    with pytest.raises(ValueError):
        chunk_document(pages, chunk_size=0, chunk_overlap=0)


def test_chunk_rejects_overlap_greater_than_or_equal_to_chunk_size() -> None:
    pages = [ExtractedPage(page_number=1, text="text")]
    with pytest.raises(ValueError):
        chunk_document(pages, chunk_size=100, chunk_overlap=100)


def test_chunk_empty_pages_list_produces_no_chunks() -> None:
    assert chunk_document([], chunk_size=1000, chunk_overlap=150) == []
