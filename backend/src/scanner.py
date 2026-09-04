"""Threat-scanning heuristics.

A pure module: given file attributes, decide whether the file looks
suspicious. Kept free of I/O so the rules are trivially testable and reused by
the Celery worker without dragging in FastAPI/database concerns.
"""

from dataclasses import dataclass
from pathlib import Path

from src.config import SCAN_SIZE_LIMIT

SUSPICIOUS_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".js"}
PDF_MIME_TYPES = {"application/pdf", "application/octet-stream"}


@dataclass(frozen=True)
class ScanResult:
    suspicious: bool
    reasons: tuple[str, ...]

    @property
    def details(self) -> str:
        return ", ".join(self.reasons) if self.reasons else "no threats found"

    @property
    def status(self) -> str:
        return "suspicious" if self.suspicious else "clean"


def scan_file(original_name: str, mime_type: str, size: int) -> ScanResult:
    """Apply the file-threat heuristics. Business logic preserved verbatim."""
    reasons: list[str] = []
    extension = Path(original_name).suffix.lower()

    if extension in SUSPICIOUS_EXTENSIONS:
        reasons.append(f"suspicious extension {extension}")

    if size > SCAN_SIZE_LIMIT:
        reasons.append("file is larger than 10 MB")

    if extension == ".pdf" and mime_type not in PDF_MIME_TYPES:
        reasons.append("pdf extension does not match mime type")

    return ScanResult(suspicious=bool(reasons), reasons=tuple(reasons))
