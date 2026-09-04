"""FileService upload lifecycle: initiate/presign/resume/complete/abort.

The service talks to repositories through an injected session; for these tests
we hand it a fake repo and a no-op session so no database is required. Storage
is real against moto's in-memory S3.
"""

import pytest
from fastapi import HTTPException

from src.config import MAX_UPLOAD_SIZE
from src.models import StoredFile
from src.services import FileService
from src.storage import UploadNotFoundError
from tests.conftest import S3_MIN_PART, make_big_part_storage, upload_all_parts


class FakeSession:
    async def commit(self):
        pass

    async def refresh(self, item):
        pass


class FakeFileRepo:
    def __init__(self):
        self.files: dict[str, StoredFile] = {}

    async def get(self, session, file_id):
        return self.files.get(file_id)

    async def create(self, session, **kwargs):
        item = StoredFile(**kwargs)
        self.files[item.id] = item
        return item

    async def delete(self, session, file_item):
        self.files.pop(file_item.id, None)

    async def update_title(self, session, file_item, title):
        file_item.title = title
        return file_item


class FakeAlertRepo:
    pass


def make_service(storage, file_repo=None) -> FileService:
    return FileService(
        storage=storage,
        file_repo=file_repo or FakeFileRepo(),
        alert_repo=FakeAlertRepo(),
    )


async def test_initiate_upload_creates_pending_file(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    result = await service.initiate_upload(
        FakeSession(),
        title="Договор",
        original_name="doc.pdf",
        size=12,
        mime_type="application/pdf",
    )
    assert result["part_size"] == 5
    assert result["num_parts"] == 3  # 12 bytes / 5-byte chunks
    item = repo.files[result["file_id"]]
    assert item.processing_status == "uploading"
    assert item.upload_id == result["upload_id"]
    assert item.stored_name == f"{item.id}.pdf"


async def test_initiate_upload_rejects_empty_file(s3):
    service = make_service(s3)
    with pytest.raises(HTTPException) as exc:
        await service.initiate_upload(
            FakeSession(),
            title="t",
            original_name="a.bin",
            size=0,
            mime_type="application/octet-stream",
        )
    assert exc.value.status_code == 422


async def test_initiate_upload_rejects_oversized_file(s3):
    service = make_service(s3)
    with pytest.raises(HTTPException) as exc:
        await service.initiate_upload(
            FakeSession(),
            title="t",
            original_name="big.bin",
            size=MAX_UPLOAD_SIZE + 1,
            mime_type="application/octet-stream",
        )
    assert exc.value.status_code == 413


async def test_initiate_upload_rejects_blank_title(s3):
    service = make_service(s3)
    with pytest.raises(HTTPException) as exc:
        await service.initiate_upload(
            FakeSession(),
            title="   ",
            original_name="a.bin",
            size=1,
            mime_type="application/octet-stream",
        )
    assert exc.value.status_code == 422


async def test_presign_parts_returns_signed_urls(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=12,
        mime_type="application/octet-stream",
    )
    signed = await service.presign_parts(FakeSession(), init["file_id"], [1, 2])
    assert [p["part_number"] for p in signed] == [1, 2]
    assert all("X-Amz-Signature=" in p["presigned_url"] for p in signed)


async def test_presign_parts_rejects_out_of_range(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=12,
        mime_type="application/octet-stream",
    )
    with pytest.raises(HTTPException) as exc:
        await service.presign_parts(FakeSession(), init["file_id"], [4])
    assert exc.value.status_code == 422


async def test_resume_upload_lists_uploaded_parts(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=12,
        mime_type="application/octet-stream",
    )
    upload_all_parts(s3, init["stored_name"], init["upload_id"], b"01234", 5)
    info = await service.resume_upload(FakeSession(), init["file_id"])
    assert info["uploaded_parts"] == [1]
    assert info["num_parts"] == 3


async def test_complete_upload_marks_file_uploaded(s3):
    # S3 refuses parts < 5 MiB at complete, so use a legal chunk size.
    big = make_big_part_storage(s3)
    repo = FakeFileRepo()
    service = make_service(big, repo)
    data = b"a" * (S3_MIN_PART + 1)
    init = await service.initiate_upload(
        FakeSession(), title="Договор", original_name="doc.pdf", size=len(data),
        mime_type="application/pdf",
    )
    upload_all_parts(
        big, init["stored_name"], init["upload_id"], data, init["part_size"]
    )
    item = await service.complete_upload(FakeSession(), init["file_id"])
    assert item.processing_status == "uploaded"
    assert item.upload_id is None
    # Object is fully assembled in S3.
    assert big.open_stream(init["stored_name"]).stream.read() == data


async def test_complete_upload_missing_parts_is_rejected(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=12,
        mime_type="application/octet-stream",
    )
    upload_all_parts(s3, init["stored_name"], init["upload_id"], b"01234", 5)
    with pytest.raises(HTTPException) as exc:
        await service.complete_upload(FakeSession(), init["file_id"])
    assert exc.value.status_code == 422


async def test_abort_upload_drops_row_and_multipart(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=12,
        mime_type="application/octet-stream",
    )
    await service.abort_upload(FakeSession(), init["file_id"])
    assert init["file_id"] not in repo.files
    with pytest.raises(UploadNotFoundError):
        s3.list_parts(init["stored_name"], init["upload_id"])


async def test_delete_file_removes_object_and_row(s3):
    big = make_big_part_storage(s3)
    repo = FakeFileRepo()
    service = make_service(big, repo)
    data = b"x" * (S3_MIN_PART + 1)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=len(data),
        mime_type="application/octet-stream",
    )
    upload_all_parts(
        big, init["stored_name"], init["upload_id"], data, init["part_size"]
    )
    await service.complete_upload(FakeSession(), init["file_id"])

    await service.delete_file(FakeSession(), init["file_id"])
    assert init["file_id"] not in repo.files
    with pytest.raises(UploadNotFoundError):
        big.open_stream(init["stored_name"])


async def test_download_returns_streaming_body(s3):
    repo = FakeFileRepo()
    service = make_service(s3, repo)
    init = await service.initiate_upload(
        FakeSession(), title="t", original_name="a.bin", size=5,
        mime_type="application/octet-stream",
    )
    upload_all_parts(
        s3, init["stored_name"], init["upload_id"], b"hello", init["part_size"]
    )
    await service.complete_upload(FakeSession(), init["file_id"])

    item, body = await service.download(FakeSession(), init["file_id"])
    assert item.id == init["file_id"]
    assert body.stream.read() == b"hello"