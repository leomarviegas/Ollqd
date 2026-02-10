"""Docling integration — AI-powered document conversion to Markdown."""

import logging
import tempfile
from pathlib import Path

log = logging.getLogger("ollqd.docling")

# Extensions that docling handles natively
DOCLING_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".html", ".htm",
    ".csv",
    ".adoc", ".asciidoc",
    ".md", ".rst",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif",
}


def is_available() -> bool:
    """Check if docling is installed without importing the full library."""
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def convert_to_markdown(
    file_path: str,
    file_bytes: bytes,
    ocr_enabled: bool = True,
    ocr_engine: str = "easyocr",
    table_structure: bool = True,
    timeout_s: float = 300,
) -> str | None:
    """Convert a document to Markdown using docling.

    Returns the Markdown string on success, or None on failure
    (so the caller can fall back to legacy parsers).
    """
    if not is_available():
        return None

    tmp_path = None
    try:
        from docling.document_converter import DocumentConverter

        # Docling needs a file path — write bytes to a temp file
        suffix = Path(file_path).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        md = result.document.export_to_markdown()

        if not md or not md.strip():
            log.warning("Docling returned empty markdown for %s", file_path)
            return None

        log.info("Docling processed %s (%d chars markdown)", file_path, len(md))
        return md

    except Exception as e:
        log.warning("Docling conversion failed for %s: %s", file_path, e)
        return None
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass
