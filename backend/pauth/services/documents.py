"""Pull plain text out of uploaded chart files (PDF, text, markdown)."""

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError


def guess_content_type(filename: str, declared: str, payload: bytes) -> str:
    """Prefer a real PDF MIME type over generic `application/octet-stream`."""
    name = filename.lower()
    declared = (declared or "").strip()
    if payload.startswith(b"%PDF") or name.endswith(".pdf"):
        return "application/pdf"
    if declared and declared != "application/octet-stream":
        return declared
    if name.endswith(".md"):
        return "text/markdown"
    if name.endswith(".txt"):
        return "text/plain"
    return declared or "application/octet-stream"


def extract_file_pages(path: str, content_type: str = "") -> list[dict]:
    """Return `[{page, text}, ...]` for a PDF or a single-page text/markdown file.

    PDFs are detected by extension, `content_type`, or a `%PDF` magic header so
    `application/octet-stream` uploads still parse.
    """
    file_path = Path(path)
    if _looks_like_pdf(file_path, content_type):
        return _extract_pdf_pages(file_path)
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return [{"page": 1, "text": text}]


def _looks_like_pdf(file_path: Path, content_type: str) -> bool:
    """True if the path, MIME type, or file header says this is a PDF."""
    if file_path.suffix.lower() == ".pdf":
        return True
    if "pdf" in (content_type or "").lower():
        return True
    try:
        with file_path.open("rb") as handle:
            return handle.read(5).startswith(b"%PDF")
    except OSError:
        return False


def _extract_pdf_pages(file_path: Path) -> list[dict]:
    """Extract selectable text per page. Encrypted PDFs are rejected."""
    try:
        reader = PdfReader(str(file_path))
        if reader.is_encrypted:
            raise ValueError(f"{file_path.name} is an encrypted PDF")
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append({"page": index, "text": page.extract_text() or ""})
        if not pages:
            return [{"page": 1, "text": ""}]
        return pages
    except FileNotDecryptedError as exc:
        raise ValueError(f"{file_path.name} is an encrypted PDF") from exc
    except PdfReadError as exc:
        raise ValueError(f"{file_path.name} could not be read as a PDF") from exc
