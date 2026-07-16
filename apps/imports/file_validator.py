"""
File security validation for imported documents.

Validates file magic bytes to detect disguised malicious files.
Extension-only validation is insufficient — this adds a second layer
by reading the file's actual binary signature (FINDING-002).
"""
import logging

logger = logging.getLogger(__name__)

# Magic byte signatures for allowed file types
# Format: extension → list of (offset, signature_bytes) tuples
# Multiple signatures per format handle variants (e.g., docx = zip format)
_MAGIC_SIGNATURES: dict[str, list[tuple[int, bytes]]] = {
    "pdf": [
        (0, b"%PDF"),  # PDF header
    ],
    "docx": [
        (0, b"PK\x03\x04"),  # ZIP/OOXML format (docx, xlsx, pptx all use ZIP)
        (0, b"PK\x05\x06"),  # Empty ZIP
        (0, b"PK\x07\x08"),  # Spanned ZIP
    ],
    "txt": [],  # Plain text has no magic bytes — accept any UTF-8 decodable content
    "md": [],   # Markdown has no magic bytes — accept any UTF-8 decodable content
}

_MIN_BYTES_TO_READ = 8


def validate_file_signature(file_content: bytes, declared_extension: str) -> tuple[bool, str]:
    """
    Validate that the file's binary signature matches the declared extension.

    Returns (is_valid, error_message).
    For txt/md files, validates UTF-8 decodability instead of magic bytes.

    Usage:
        is_valid, error = validate_file_signature(content, "pdf")
        if not is_valid:
            raise ValidationError({"file": error})
    """
    ext = declared_extension.lower().lstrip(".")

    if ext not in _MAGIC_SIGNATURES:
        return False, f"Unsupported file type: .{ext}"

    signatures = _MAGIC_SIGNATURES[ext]

    # Text formats — validate UTF-8 decodability
    if ext in ("txt", "md"):
        return _validate_text_file(file_content, ext)

    # Binary formats — check magic bytes
    if not signatures:
        return True, ""

    header = file_content[:_MIN_BYTES_TO_READ]
    for offset, signature in signatures:
        if header[offset:offset + len(signature)] == signature:
            return True, ""

    logger.warning(
        "File signature mismatch: declared=%s, header=%s",
        ext,
        header[:8].hex(),
    )
    return False, (
        f"File content does not match the declared type '.{ext}'. "
        "The file may be corrupted or renamed."
    )


def _validate_text_file(content: bytes, ext: str) -> tuple[bool, str]:
    """Validate that a text file is valid UTF-8 and not empty."""
    if len(content) == 0:
        return False, f"The uploaded .{ext} file is empty."

    # Reject if it looks like a binary file (many non-printable bytes)
    null_byte_count = content[:1024].count(b"\x00")
    if null_byte_count > 10:
        return False, (
            f"The uploaded file does not appear to be a valid .{ext} text file. "
            "Binary content detected."
        )

    try:
        content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            # Fallback: accept latin-1 (common for legacy resumes)
            content.decode("latin-1", errors="strict")
        except UnicodeDecodeError:
            return False, f"The .{ext} file contains invalid character encoding."

    return True, ""
