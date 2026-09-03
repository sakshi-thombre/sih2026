"""Unit tests for document text extraction. No real Ollama or network
access required.

For the "valid PDF" case we mock `pypdf.PdfReader` (analogous to
mocking httpx's transport for OllamaProvider tests) rather than hand-
building PDF bytes with real extractable text, since pypdf's own
parsing correctness is out of scope here — we're testing our loader's
page iteration, cleaning, and error mapping.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from docx import Document as DocxDocument

from app.core.exceptions import InvalidDocumentError
from app.rag.loaders import load_document


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    buffer = io.BytesIO()
    document = DocxDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(buffer)
    return buffer.getvalue()


def test_load_valid_txt() -> None:
    content = b"Pressure relief valves protect equipment from overpressure."
    document = load_document("sop.txt", content)

    assert document.file_type == "txt"
    assert len(document.pages) == 1
    assert document.pages[0].page_number is None
    assert "Pressure relief valves" in document.pages[0].text


def test_load_valid_pdf() -> None:
    fake_page_1 = MagicMock()
    fake_page_1.extract_text.return_value = "Page one safety content."
    fake_page_2 = MagicMock()
    fake_page_2.extract_text.return_value = "Page two safety content."

    fake_reader = MagicMock()
    fake_reader.pages = [fake_page_1, fake_page_2]

    with patch("app.rag.loaders.PdfReader", return_value=fake_reader):
        document = load_document("report.pdf", b"%PDF-1.4\nsome pdf bytes")

    assert document.file_type == "pdf"
    assert len(document.pages) == 2
    assert document.pages[0].page_number == 1
    assert document.pages[1].page_number == 2
    assert "Page one" in document.pages[0].text


def test_load_valid_docx() -> None:
    content = _make_docx_bytes(["Unit 3 incident summary.", "No injuries reported."])
    document = load_document("incident.docx", content)

    assert document.file_type == "docx"
    assert len(document.pages) == 1
    assert document.pages[0].page_number is None
    assert "Unit 3 incident summary" in document.pages[0].text
    assert "No injuries reported" in document.pages[0].text


def test_reject_empty_file() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("empty.txt", b"")


def test_reject_unsupported_extension() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("data.csv", b"a,b,c\n1,2,3")


def test_reject_document_with_no_extension() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("noextension", b"some content")


def test_reject_corrupt_pdf() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("broken.pdf", b"%PDF-1.4\n" + b"not a real pdf stream" * 20)


def test_reject_pdf_missing_magic_bytes() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("fake.pdf", b"this is not a pdf at all")


def test_reject_corrupt_docx() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("broken.docx", b"PK" + b"not a real zip" * 10)


def test_reject_docx_missing_magic_bytes() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("fake.docx", b"this is not a docx at all")


def test_reject_pdf_with_no_extractable_text() -> None:
    fake_page = MagicMock()
    fake_page.extract_text.return_value = ""
    fake_reader = MagicMock()
    fake_reader.pages = [fake_page]

    with patch("app.rag.loaders.PdfReader", return_value=fake_reader):
        with pytest.raises(InvalidDocumentError):
            load_document("blank.pdf", b"%PDF-1.4\nsome pdf bytes")


def test_reject_whitespace_only_txt() -> None:
    with pytest.raises(InvalidDocumentError):
        load_document("whitespace.txt", b"   \n\n   \t  ")
