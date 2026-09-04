"""File metadata extraction.

Pure helpers used by the Celery worker to enrich a stored file with simple
derived metrics (line/char counts for text, page count for PDFs).
"""

from pathlib import Path


def extract_metadata(
    path: Path, original_name: str, mime_type: str, size: int
) -> dict:
    """Build the metadata dict for a stored file. Behaviour matches the
    original implementation exactly."""
    metadata: dict = {
        "extension": Path(original_name).suffix.lower(),
        "size_bytes": size,
        "mime_type": mime_type,
    }

    if mime_type.startswith("text/"):
        content = path.read_text(encoding="utf-8", errors="ignore")
        metadata["line_count"] = len(content.splitlines())
        metadata["char_count"] = len(content)
    elif mime_type == "application/pdf":
        content = path.read_bytes()
        metadata["approx_page_count"] = max(content.count(b"/Type /Page"), 1)

    return metadata
