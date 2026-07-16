# Import all parsers to trigger __init_subclass__ registration
from apps.imports.parsers.txt_parser import TxtParser  # noqa: F401
from apps.imports.parsers.markdown_parser import MarkdownParser  # noqa: F401
from apps.imports.parsers.docx_parser import DocxParser  # noqa: F401
from apps.imports.parsers.pdf_parser import PdfParser  # noqa: F401
