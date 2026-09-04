"""S3StorageService: multipart lifecycle, presigning, whole-object operations.

Parts are uploaded through the real boto3 multipart API (moto emulates S3);
the presigned-URL helper is checked structurally since no live MinIO runs in
unit tests. The full-flow tests (the ones that call ``complete``) use the S3
minimum legal chunk size (5 MiB); moto enforces it exactly like MinIO do.

"""

import pytest

from src.storage import S3StorageService, UploadNotFoundError
from tests.conftest import S3_MIN_PART, make_big_part_storage


def upload_all_parts(
    storage: S3StorageService, key: str, upload_id: str, data: bytes, part_size: int
) -> list[dict]:
    """Upload ``data`` via the boto3 multipart API — mirrors the browser PUT."""
    parts: list[dict] = []
    offset, number = 0, 1
    while offset < len(data):
        chunk = data[offset : offset + part_size]
        response = storage._client.upload_part(
            Bucket=storage.bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=number,
            Body=chunk,
        )
        parts.append({"PartNumber": number, "ETag": response["ETag"]})
        offset += len(chunk)
        number += 1
    return parts


def test_create_multipart_upload_returns_upload_id(s3):
    upload_id = s3.create_multipart_upload("abc.txt")
    assert isinstance(upload_id, str) and upload_id


def test_presign_upload_part_returns_signed_put_url(s3):
    upload_id = s3.create_multipart_upload("path/file.bin")
    url = s3.presign_upload_part("path/file.bin", upload_id, 3)
    assert "X-Amz-Signature=" in url
    assert "partNumber=3" in url
    assert "uploadId=" in url


def test_list_parts_reports_uploaded_part_numbers(s3):
    key = "a.bin"
    upload_id = s3.create_multipart_upload(key)
    upload_all_parts(s3, key, upload_id, b"0123456789", 5)
    assert s3.uploaded_part_numbers(key, upload_id) == {1, 2}


def test_complete_multipart_upload_assembles_object(s3, tmp_path):
    big = make_big_part_storage(s3)
    key = "doc.pdf"
    upload_id = big.create_multipart_upload(key)
    data = b"a" * S3_MIN_PART + b"tail"
    parts = upload_all_parts(big, key, upload_id, data, S3_MIN_PART)
    big.complete_multipart_upload(key, upload_id, parts)

    dest = tmp_path / "out.pdf"
    big.download_to_path(key, str(dest))
    assert dest.read_bytes() == data


def test_abort_multipart_upload_throws_upload_not_found(s3):
    key = "abandoned.bin"
    upload_id = s3.create_multipart_upload(key)
    upload_all_parts(s3, key, upload_id, b"data", 4)
    s3.abort_multipart_upload(key, upload_id)

    with pytest.raises(UploadNotFoundError):
        s3.list_parts(key, upload_id)


def test_delete_removes_object(s3):
    big = make_big_part_storage(s3)
    key = "gone.txt"
    upload_id = big.create_multipart_upload(key)
    parts = upload_all_parts(big, key, upload_id, b"x" * S3_MIN_PART, S3_MIN_PART)
    big.complete_multipart_upload(key, upload_id, parts)

    big.delete(key)

    with pytest.raises(UploadNotFoundError):
        big.iter_object(key)


def test_download_to_path_missing_object_raises(s3, tmp_path):
    with pytest.raises(UploadNotFoundError):
        s3.download_to_path("does-not-exist.txt", str(tmp_path / "x"))


def test_num_parts_for_size(s3):
    assert s3.num_parts_for(0) == 0
    assert s3.num_parts_for(1) == 1
    assert s3.num_parts_for(s3.part_size) == 1
    assert s3.num_parts_for(s3.part_size + 1) == 2
    assert s3.num_parts_for(3 * s3.part_size) == 3