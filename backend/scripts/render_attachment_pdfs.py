"""Render dummy chart PDFs from the sibling .txt attachments."""

from pathlib import Path

from fpdf import FPDF

ATTACHMENTS = Path(__file__).resolve().parent.parent / "pauth" / "fixtures" / "attachments"


class ChartPdf(FPDF):
    """Simple letter-size PDF with extractable Helvetica text."""

    def header(self) -> None:
        """No running header; chart dumps are full-page notes."""
        return


def render_text_to_pdf(source: Path, dest: Path) -> None:
    """Write `source` as a multi-page PDF that pypdf can extract."""
    pdf = ChartPdf(format="Letter")
    pdf.set_margins(left=18, top=18, right=18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(w=usable, h=6, text=line if line else " ")
    dest.write_bytes(bytes(pdf.output()))


def main() -> None:
    """Create a .pdf next to each .txt attachment except README."""
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    for source in sorted(ATTACHMENTS.glob("*.txt")):
        if source.name.upper() == "README.TXT":
            continue
        dest = source.with_suffix(".pdf")
        render_text_to_pdf(source, dest)
        print(dest.name)


if __name__ == "__main__":
    main()
