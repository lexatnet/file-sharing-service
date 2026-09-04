"""S3 (MinIO) file storage service.

Uploaded files live in an S3 bucket (MinIO in docker-compose) instead of the
local disk. The client uploads file chunks directly to S3 through presigned
PUT URLs, so the backend only orchestrates the multipart-upload lifecycle
(create/presign/list/complete/abort) and never buffers file bodies in memory.

Two boto3 clients are used: one talks to the endpoint reachable from inside the
compose network (``s3:9000``); the other only signs presigned URLs against the
endpoint the browser can reach (``localhost:9000``). Presigning does not make a
network call, so the two endpoints stay distinct.
"""

from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.config import Settings


class StorageError(Exception):
    """Raised when a stored object cannot be created/read/removed."""


class FileTooLargeError(StorageError):
    """Raised when an upload exceeds the caller-provided size cap."""


class UploadNotFoundError(StorageError):
    """Raised when a multipart upload or stored object does not exist."""


@dataclass
class S3Object:
    """Typed view over a boto3 ``get_object`` response.



    The HTTP layer streams ``stream`` without touching the raw dict, keeping the
    knowledge of boto3's response shape in a single place..
    """
    _response: dict

    @property
    def stream(self) -> Any:
        """File-like stream of the object's body (a boto3 ``StreamingBody``)."""
        return self._response["Body"]


class S3StorageService:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.part_size = settings.s3_part_size
        # Path-style addressing + SigV4 are required by MinIO.
        config = Config(s3={"addressing_style": "path"}, signature_version="s3v4")
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=config,
        )
        # Client used only for generating presigned URLs reachable by browsers.
        self._presign_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=config,
        )

    def num_parts_for(self, size: int) -> int:
        """Number of ``part_size`` chunks a payload of ``size`` bytes splits into."""
        if size <= 0:
            return 0
        return (size + self.part_size - 1) // self.part_size

    # --- multipart upload lifecycle -----------------------------------------

    def create_multipart_upload(self, key: str) -> str:
        """Start a multipart upload and return its S3 ``UploadId``.

        A multipart upload is durable in S3: uploaded parts survive until the
        upload is completed or aborted, which is what makes client-side resume
        possible (see ``presign_upload_part``/``list_part_numbers``).
        """
        response = self._client.create_multipart_upload(Bucket=self.bucket, Key=key)
        return response["UploadId"]

    def presign_upload_part(self, key: str, upload_id: str, part_number: int) -> str:
        """Presigned PUT URL a browser uses to upload one chunk directly to S3."""
        return self._presign_client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            HttpMethod="PUT",
            ExpiresIn=3600,
        )

    def list_parts(self, key: str, upload_id: str) -> list[dict]:
        """All uploaded parts of a multipart upload as ``{PartNumber, ETag}``."""
        parts: list[dict] = []
        marker: str | None = None
        while True:
            kwargs: dict = {"Bucket": self.bucket, "Key": key, "UploadId": upload_id}
            if marker:
                kwargs["PartNumberMarker"] = marker
            try:
                response = self._client.list_parts(**kwargs)
            except ClientError as exc:
                raise UploadNotFoundError(
                    "Multipart upload does not exist or was completed"
                ) from exc
            parts.extend(
                {"PartNumber": p["PartNumber"], "ETag": p["ETag"]}
                for p in response.get("Parts", [])
            )
            if not response.get("IsTruncated"):
                return parts
            marker = response.get("NextPartNumberMarker")

    def uploaded_part_numbers(self, key: str, upload_id: str) -> set[int]:
        """Part numbers already uploaded — used by resume to skip them."""
        return {part["PartNumber"] for part in self.list_parts(key, upload_id)}

    def complete_multipart_upload(
        self, key: str, upload_id: str, parts: list[dict]
    ) -> None:
        """Assemble uploaded parts into a single S3 object."""
        try:
            self._client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except ClientError as exc:
            raise StorageError(
                f"Cannot complete multipart upload: S3 returned {exc.response.get('Error', {}).get('Code')}"
            ) from exc

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        """Discard a multipart upload and any parts uploaded so far."""
        try:
            self._client.abort_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id
            )
        except ClientError as exc:
            raise UploadNotFoundError(
                "Multipart upload does not exist or was completed"
            ) from exc

    # --- whole-object operations --------------------------------------------

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"Failed to delete object {key}") from exc

    def download_to_path(self, key: str, dest_path: str) -> None:
        """Download a stored object to a local file (used by the worker)."""
        try:
            self._client.download_file(self.bucket, key, dest_path)
        except ClientError as exc:
            raise UploadNotFoundError(f"Stored object {key} not found") from exc

    def open_stream(self, key: str) -> S3Object:
        """Return a typed body stream for downloading an object..

        The caller streams ``stream`` (a boto3 ``StreamingBody``) so the
        HTTP layer never buffers the object in memory..
        """
        try:
            return S3Object(self._client.get_object(Bucket=self.bucket, Key=key))
        except ClientError as exc:
            raise UploadNotFoundError(f"Stored object {key} not found") from exc