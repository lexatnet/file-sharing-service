"""Metadata extraction: text line/char counts and PDF page approximation."""

from src.metadata import extract_metadata


def test_text_file_counts_lines_and_chars(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("line one\nline two\n", encoding="utf-8")

    meta = extract_metadata(path, "notes.txt", "text/plain", 20)
    assert meta["extension"] == ".txt"
    assert meta["size_bytes"] == 20
    assert meta["mime_type"] == "text/plain"
    assert meta["line_count"] == 2
    assert meta["char_count"] == 18  # "line one" (8) + "\n" + "line two" (8) + "\n"


def test_pdf_counts_page_markers(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"junk /Type /Page junk /Type /Page")

    meta = extract_metadata(path, "doc.pdf", "application/pdf", 32)
    assert meta["approx_page_count"] == 2


def test_pdf_with_no_markers_defaults_to_one_page(tmp_path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"no page objects here")

    meta = extract_metadata(path, "doc.pdf", "application/pdf", 23)
    assert meta["approx_page_count"] == 1


def test_binary_file_has_no_extra_fields(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"\x00\x01\x02")

    meta = extract_metadata(path, "data.bin", "application/octet-stream", 3)
    assert meta == {
        "extension": ".bin",
        "size_bytes": 3,
        "mime_type": "application/octet-stream",
    }


def test_extension_is_lowercased(tmp_path):
    path = tmp_path / "DOC.PDF"
    path.write_bytes(b"")
    meta = extract_metadata(path, "DOC.PDF", "application/pdf", 0)
    assert meta["extension"] == ".pdf"