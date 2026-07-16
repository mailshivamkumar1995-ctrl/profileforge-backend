from apps.imports.parsers import DocumentParser


class PdfParser(DocumentParser):
    extension = "pdf"

    def parse(self, file_path: str) -> str:
        # Try pdfminer first, fall back to PyMuPDF
        try:
            return self._parse_pdfminer(file_path)
        except ImportError:
            pass

        try:
            return self._parse_pymupdf(file_path)
        except ImportError:
            raise RuntimeError(
                "A PDF library is required for PDF import. "
                "Install one: pip install pdfminer.six  or  pip install pymupdf"
            )

    @staticmethod
    def _parse_pdfminer(file_path: str) -> str:
        from pdfminer.high_level import extract_text
        text = extract_text(file_path)
        return text or ""

    @staticmethod
    def _parse_pymupdf(file_path: str) -> str:
        import fitz  # PyMuPDF
        parts: list[str] = []
        with fitz.open(file_path) as doc:
            for page in doc:
                parts.append(page.get_text())
        return "\n".join(parts)
