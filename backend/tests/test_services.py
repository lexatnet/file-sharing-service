"""FileService business rules: title/empty/oversize validation and delegation.

The service talks to repositories through an injected session; for these tests
we hand it a fake repo so no database is required.
"""

from datetime import datetime

import pytest
from fastapi import HTTPException

from src.config import MAX_UPLOAD_SIZE
from src.models import StoredFile
from src.services import FileService


class FakeUpload:
    """Stand-in for fastapi.UploadFile: yields preset byte chunks."""

    def __init__(self, chunks: list[bytes], filename: str = "doc.pdf",
                 content_type: str = "application/pdf"):
        self.chunks = chunks
        self.filename = filename
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


class FakeFileRepo:
    def __init__(self):
        self.created = []

    async def create(self, session, **kwargs) -> StoredFile:
        item = StoredFile(**kwargs)
        self.created.append(item)
        return item


class FakeAlertRepo:
    pass


def make_service(storage, file_repo=None, alert_repo=None) -> FileService:
    return FileService(
        storage=storage,
        file_repo=file_repo or FakeFileRepo(),
        alert_repo=alert_repo or FakeAlertRepo(),
    )


async def test_empty_upload_is_rejected(storage):
    service = make_service(storage)
    with pytest.raises(HTTPException) as exc:
        await service.create_file(
            None,  # session — unused on the validation paths
            "test",
            FakeUpload([b""], filename="empty.bin", content_type="application/octet-stream"),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "File is empty"


async def test_oversized_upload_is_rejected_and_cleaned_up(storage):
    service = make_service(storage)
    # Build a body larger than the cap to trigger the streaming abort.
    chunk = b"x" * 64 * 1024
    upload = FakeUpload([chunk] * 2000, filename="big.bin", content_type="application/octet-stream")
    with pytest.raises(HTTPException) as exc:
        await service.create_file(None, "big", upload)
    assert exc.value.status_code == 413
    assert exc.value.detail == "File is too large"
    # The partial file must not linger on disk.
    assert not any(storage.storage_dir.iterdir())


async def test_blank_title_is_rejected(storage):
    service = make_service(storage)
    with pytest.raises(HTTPException) as exc:
        await service.create_file(None, "   ", FakeUpload([b"x"]))
    assert exc.value.status_code == 422


async def test_happy_path_creates_file(storage):
    file_repo = FakeFileRepo()
    service = make_service(storage, file_repo=file_repo)
    item = await service.create_file(
        None,
        "Договор",
        FakeUpload([b"pdf-data"], filename="doc.pdf", content_type="application/pdf"),
    )
    assert item.title == "Договор"
    assert item.original_name == "doc.pdf"
    assert item.stored_name == f"{item.id}.pdf"
    assert item.mime_type == "application/pdf"
    assert item.size == len(b"pdf-data")
    assert item.processing_status == "uploaded"
    assert len(file_repo.created) == 1
    assert (storage.storage_dir / item.stored_name).exists()