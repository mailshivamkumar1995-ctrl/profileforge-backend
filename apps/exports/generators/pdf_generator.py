from apps.exports.generators import DocumentGenerator


class PdfGenerator(DocumentGenerator):
    """
    HTML → PDF generator using WeasyPrint.
    Produces a byte-perfect replica of the rendered HTML template.
    Preview == Export invariant is maintained — the same HTML is used for both.
    """

    format = "pdf"

    def generate(self, html_content: str, profile_data: dict | None = None, template_slug: str | None = None) -> bytes:
        try:
            from weasyprint import HTML as WeasyHTML
            from weasyprint.text.fonts import FontConfiguration

            font_config = FontConfiguration()
            doc = WeasyHTML(
                string=html_content,
                base_url=None,
            )
            return doc.write_pdf(font_config=font_config)
        except ImportError:
            raise RuntimeError(
                "WeasyPrint is required for PDF export. "
                "Install it: pip install weasyprint"
            )
        except Exception as exc:
            raise RuntimeError(f"PDF generation failed: {exc}") from exc
