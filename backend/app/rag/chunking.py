"""Deterministic text chunking.

Chunks are produced per-page with a character-based sliding window, so
a chunk never mixes text from two different (known) pages — this keeps
the page-number citation on each chunk accurate instead of approximate.
For formats with no page concept (TXT/DOCX), the whole document is one
"page" and is chunked the same way.

No randomness, no external calls — same input always produces the same
output, which the test suite relies on.
"""

from pydantic import BaseModel

from app.rag.loaders import ExtractedPage


class Chunk(BaseModel):
    text: str
    chunk_index: int
    page_number: int | None


def chunk_document(pages: list[ExtractedPage], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

    step = chunk_size - chunk_overlap
    chunks: list[Chunk] = []
    index = 0

    for page in pages:
        text = page.text
        length = len(text)
        if length == 0:
            continue

        start = 0
        while start < length:
            end = min(start + chunk_size, length)
            piece = text[start:end].strip()
            if piece:
                chunks.append(Chunk(text=piece, chunk_index=index, page_number=page.page_number))
                index += 1
            if end == length:
                break
            start += step

    return chunks
