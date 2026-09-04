"""Business-logic / orchestration layer.

FileService coordinates the S3 multipart upload lifecycle (init/presign/
resume/complete/abort) and the repositories (DB). Upload bodies never transit
the backend: the client uploads chunks straight to S3 through presigned URLs;
the backend only creates the multipart upload, hands out signed chunk URLs,
lists already-uploaded parts (for resume) and completes/aborts the upload.
Session objects are passed in by the API layer (via FastAPI DI) so a single
transaction spans the whole operation.
"""

from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import MAX_UPLOAD_SIZE
from src.models import Alert, StoredFile
from src.repositories import AlertRepository, FileRepository
from src.storage import (
    S3Object,
    S3StorageService,
    StorageError,
    UploadNotFoundError,
)

# Multipart part numbers are 1-based (S3 requirement).
_MIN_PART_NUMBER = 1


def _freeform_filename(name: str) -> str:
    """URL-encode unsafe characters for a ``filename*=`` content-disposition."""
    return quote(name)


def _validate_title(title: str) -> str:
    """Strip and reject a blank title — shared by create/update paths."""
    title = title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title must not be empty",
        )
    return title


class FileService:
    def __init__(
        self,
        storage: S3StorageService,
        file_repo: FileRepository,
        alert_repo: AlertRepository,
    ) -> None:
        self.storage = storage
        self.file_repo = file_repo
        self.alert_repo = alert_repo

    # --- queries -------------------------------------------------------------

    async def list_files(self, session: AsyncSession) -> list[StoredFile]:
        return await self.file_repo.list_all(session)

    async def list_alerts(self, session: AsyncSession) -> list[Alert]:
        return await self.alert_repo.list_all(session)

    async def get_file(self, session: AsyncSession, file_id: str) -> StoredFile:
        file_item = await self.file_repo.get(session, file_id)
        if file_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
            )
        return file_item

    # --- upload lifecycle ----------------------------------------------------

    async def initiate_upload(
        self,
        session: AsyncSession,
        *,
        title: str,
        original_name: str,
        size: int,
        mime_type: str,
    ) -> dict:
        """Open a new S3 multipart upload and register the pending file row.

        Returns the info the client needs to slice the file and upload the
        chunks: ``upload_id``, ``part_size``, ``num_parts``. The row is created
        with ``processing_status="uploading"`` so interrupted uploads are
        resumable (the UploadId persists across restarts) yet never requeued by
        the startup sweep (which only targets ``uploaded``/``processing``).
        """
        title = _validate_title(title)
        if size <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File is empty",
            )
        if size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File is too large",
            )

        file_id = str(uuid4())
        stored_name = f"{file_id}{Path(original_name).suffix}"

        upload_id = self.storage.create_multipart_upload(stored_name)

        file_item = await self.file_repo.create(
            session,
            id=file_id,
            title=title,
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size=size,
            upload_id=upload_id,
            processing_status="uploading",
        )

        return {
            "file_id": file_item.id,
            "stored_name": file_item.stored_name,
            "upload_id": upload_id,
            "part_size": self.storage.part_size,
            "num_parts": self.storage.num_parts_for(size),
        }

    async def presign_parts(
        self, session: AsyncSession, file_id: str, part_numbers: list[int]
    ) -> list[dict]:
        """Presigned PUT URLs for the given chunk numbers of a pending upload."""
        file_item = await self._require_pending_upload(session, file_id)
        max_part = self.storage.num_parts_for(file_item.size)
        if any(n < _MIN_PART_NUMBER or n > max_part for n in part_numbers):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Part number out of range",
            )
        return [
            {
                "part_number": n,
                "presigned_url": self.storage.presign_upload_part(
                    file_item.stored_name, file_item.upload_id, n
                ),
            }
            for n in part_numbers
        ]

    async def resume_upload(self, session: AsyncSession, file_id: str) -> dict:
        """Upload info for resuming: which chunks are already in S3."""
        file_item = await self._require_pending_upload(session, file_id)
        uploaded = self.storage.uploaded_part_numbers(
            file_item.stored_name, file_item.upload_id
        )
        return {
            "file_id": file_item.id,
            "upload_id": file_item.upload_id,
            "part_size": self.storage.part_size,
            "num_parts": self.storage.num_parts_for(file_item.size),
            "uploaded_parts": sorted(uploaded),
        }

    async def complete_upload(self, session: AsyncSession, file_id: str) -> StoredFile:
        """Assemble all uploaded chunks in S3 and mark the file as uploaded."""
        file_item = await self._require_pending_upload(session, file_id)
        num_parts = self.storage.num_parts_for(file_item.size)
        parts = self.storage.list_parts(
            file_item.stored_name, file_item.upload_id
        )
        missing = set(range(_MIN_PART_NUMBER, num_parts + 1)) - {
            p["PartNumber"] for p in parts
        }
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot complete: parts {sorted(missing)} not uploaded",
            )

        try:
            self.storage.complete_multipart_upload(
                file_item.stored_name, file_item.upload_id, parts
            )
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Could not complete the multipart upload: {exc}",
            ) from exc

        file_item.upload_id = None
        file_item.processing_status = "uploaded"
        await session.commit()
        await session.refresh(file_item)
        return file_item

    async def abort_upload(self, session: AsyncSession, file_id: str) -> None:
        """Discard the multipart upload in S3 and drop the pending row."""
        file_item = await self._require_pending_upload(session, file_id)
        try:
            self.storage.abort_multipart_upload(
                file_item.stored_name, file_item.upload_id
            )
        except UploadNotFoundError:
            pass  # already gone server-side — delete the local row anyway
        await self.file_repo.delete(session, file_item)

    async def _require_pending_upload(
        self, session: AsyncSession, file_id: str
    ) -> StoredFile:
        """Resolve a file row that still has an active (unfinished) upload."""
        file_item = await self.get_file(session, file_id)
        if not file_item.upload_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Upload already completed or not found",
            )
        return file_item

    # --- CRUD ----------------------------------------------------------------

    async def update_file(
        self, session: AsyncSession, file_id: str, title: str
    ) -> StoredFile:
        title = _validate_title(title)
        file_item = await self.get_file(session, file_id)
        return await self.file_repo.update_title(session, file_item, title)

    async def delete_file(self, session: AsyncSession, file_id: str) -> None:
        file_item = await self.get_file(session, file_id)
        try:
            self.storage.delete(file_item.stored_name)
        except StorageError:
            pass  # object already gone — drop the DB row regardless
        await self.file_repo.delete(session, file_item)

    async def download(
        self, session: AsyncSession, file_id: str
    ) -> tuple[StoredFile, S3Object]:
        """Resolve a stored file to its S3 body stream, or 404."""
        file_item = await self.get_file(session, file_id)
        try:
            body = self.storage.open_stream(file_item.stored_name)
        except UploadNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found",
            ) from exc
        return file_item, body

    @staticmethod
    def download_name(file_item: StoredFile) -> str:
        """Content-Disposition ``filename*=...`` value for the original name."""
        return f"attachment; filename*=UTF-8''{_freeform_filename(file_item.original_name)}"