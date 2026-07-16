# Import all generators to trigger __init_subclass__ registration
from apps.exports.generators.pdf_generator import PdfGenerator  # noqa: F401
from apps.exports.generators.docx_generator import DocxGenerator  # noqa: F401
