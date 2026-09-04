"""Threat-scanning heuristics are the core business rule — lock them down."""

import pytest

from src.config import SCAN_SIZE_LIMIT
from src.scanner import ScanResult, scan_file


def test_clean_file():
    result = scan_file("report.pdf", "application/pdf", 1024)
    assert isinstance(result, ScanResult)
    assert not result.suspicious
    assert result.status == "clean"
    assert result.details == "no threats found"


@pytest.mark.parametrize(
    "name, mime, size, expected_reason",
    [
        ("evil.exe", "application/octet-stream", 10, "suspicious extension .exe"),
        ("evil.bat", "text/plain", 10, "suspicious extension .bat"),
        ("evil.cmd", "text/plain", 10, "suspicious extension .cmd"),
        ("evil.sh", "text/x-shellscript", 10, "suspicious extension .sh"),
        ("evil.js", "text/javascript", 10, "suspicious extension .js"),
    ],
)
def test_suspicious_extensions(name, mime, size, expected_reason):
    result = scan_file(name, mime, size)
    assert result.suspicious
    assert result.status == "suspicious"
    assert expected_reason in result.reasons


def test_extension_check_is_case_insensitive():
    result = scan_file("EVIL.EXE", "application/octet-stream", 10)
    assert result.suspicious


def test_large_file_is_suspicious():
    result = scan_file("data.bin", "application/octet-stream", SCAN_SIZE_LIMIT + 1)
    assert result.suspicious
    assert result.reasons == ("file is larger than 10 MB",)


def test_pdf_mime_mismatch_is_suspicious():
    result = scan_file("doc.pdf", "text/plain", 10)
    assert result.suspicious
    assert "pdf extension does not match mime type" in result.reasons


def test_pdf_with_pdf_mime_is_clean():
    result = scan_file("doc.pdf", "application/pdf", 10)
    assert not result.suspicious


def test_multiple_reasons_accumulate():
    # .exe flagged for extension AND size (pdf-mismatch only applies to .pdf).
    result = scan_file("evil.exe", "text/plain", SCAN_SIZE_LIMIT + 1)
    assert set(result.reasons) == {
        "suspicious extension .exe",
        "file is larger than 10 MB",
    }
    assert result.status == "suspicious"