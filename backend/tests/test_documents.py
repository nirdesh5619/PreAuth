from pathlib import Path

from pauth.services.documents import extract_file_pages, guess_content_type

ATTACHMENTS = Path(__file__).resolve().parent.parent / "pauth" / "fixtures" / "attachments"


def test_guess_content_type_sniffs_pdf_magic():
    """A PDF header should win over a generic octet-stream MIME type."""
    assert (
        guess_content_type("chart.bin", "application/octet-stream", b"%PDF-1.4 rest")
        == "application/pdf"
    )


def test_extract_fixture_pdf(tmp_path: Path):
    """Dummy Quantiferon PDF must yield extractable lab text, including via magic sniff."""
    dest = ATTACHMENTS / "AR-quantiferon-lab.pdf"
    pages = extract_file_pages(str(dest), "application/pdf")
    blob = " ".join(page["text"] for page in pages)
    assert "NEGATIVE" in blob
    mystery = tmp_path / "chart.bin"
    mystery.write_bytes(dest.read_bytes())
    sniffed = extract_file_pages(str(mystery), "application/octet-stream")
    assert "NEGATIVE" in sniffed[0]["text"]
