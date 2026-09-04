"""StorageService: streaming save, size cap, and path-traversal guard."""

import pytest

from src.storage import FileTooLargeError, StorageError, StorageService


class FakeUpload:
    """Minimal async upload stand-in: iterates over preset byte chunks."""

    def __init__(self, chunks: list[bytes], content_type: str = "application/octet-stream"):
        self.chunks = chunks
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        if self.chunks:
            return self.chunks.pop(0)
        return b""


@pytest.fixture
def upload() -> FakeUpload:
    return FakeUpload([b"hello", b" world"])


async def test_save_streams_bytes_and_reports_size_mime(storage, upload):
    size, mime = await storage.save(upload, "abc.txt")
    assert size == len(b"hello world")
    assert mime == "application/octet-stream"
    assert (storage.storage_dir / "abc.txt").read_bytes() == b"hello world"


async def test_save_defaults_mime_from_extension(storage):
    upload = FakeUpload([b"data"], content_type=None)
    size, mime = await storage.save(upload, "report.pdf")
    assert mime == "application/pdf"


async def test_save_rejects_oversized_upload_and_cleans_up(storage):
    # First chunk lands exactly on the cap, the second pushes past it.
    upload = FakeUpload([b"0123456789", b"1"], content_type=None)
    with pytest.raises(FileTooLargeError):
        await storage.save(upload, "big.bin", max_size=10)
    assert not (storage.storage_dir / "big.bin").exists()


async def test_save_accepts_upload_at_exact_limit(storage, tmp_path):
    upload = FakeUpload([b"0123456789"], content_type=None)
    size, _ = await storage.save(upload, "ok.bin", max_size=10)
    assert size == 10
    assert (storage.storage_dir / "ok.bin").read_bytes() == b"0123456789"


async def test_delete_removes_file(storage):
    (storage.storage_dir / "gone.txt").write_text("x")
    storage.delete("gone.txt")
    assert not (storage.storage_dir / "gone.txt").exists()


async def test_delete_missing_file_is_noop(storage):
    storage.delete("never-existed.txt")


def test_resolve_rejects_path_traversal(storage):
    with pytest.raises(StorageError):
        storage.resolve("../outside.txt")
    with pytest.raises(StorageError):
        storage.resolve("sub/../../outside.txt")


def test_resolve_allows_nested_names(storage):
    nested = storage.storage_dir / "sub"
    nested.mkdir()
    assert storage.resolve("sub/nested.txt") == (nested / "nested.txt").resolve()


def test_constructor_creates_directory(tmp_path):
    target = tmp_path / "brand" / "new"
    StorageService(target)
    assert target.is_dir()