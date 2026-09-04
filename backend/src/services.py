"""Business-logic / orchestration layer.

FileService coordinates storage (disk) and repositories (DB) and encodes the
upload/update/delete/download rules. Session objects are passed in by the API
layer (via FastAPI DI) so a single transaction spans the whole operation.
"""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import MAX_UPLOAD_SIZE
from src.models import Alert, StoredFile
from src.repositories import AlertRepository, FileRepository
from src.storage import FileTooLargeError, StorageError, StorageService


class FileService:
    def __init__(
        self,
        storage: StorageService,
        file_repo: FileRepository,
        alert_repo: AlertRepository,
    ) -> None:
        self.storage = storage
        self.file_repo = file_repo
        self.alert_repo = alert_repo

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

    async def create_file(
        self, session: AsyncSession, title: str, upload_file: UploadFile
    ) -> StoredFile:
        title = title.strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Title must not be empty",
            )

        file_id = str(uuid4())
        original_name = upload_file.filename or f"{file_id}"
        suffix = Path(original_name).suffix
        stored_name = f"{file_id}{suffix}"

        try:
            size, mime_type = await self.storage.save(
                upload_file, stored_name, max_size=MAX_UPLOAD_SIZE
            )
        except FileTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File is too large",
            ) from exc

        if size == 0:
            self.storage.delete(stored_name)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty"
            )

        return await self.file_repo.create(
            session,
            id=file_id,
            title=title,
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size=size,
            processing_status="uploaded",
        )

    async def update_file(
        self, session: AsyncSession, file_id: str, title: str
    ) -> StoredFile:
        title = title.strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Title must not be empty",
            )
        file_item = await self.get_file(session, file_id)
        return await self.file_repo.update_title(session, file_item, title)

    async def delete_file(self, session: AsyncSession, file_id: str) -> None:
        file_item = await self.get_file(session, file_id)
        self.storage.delete(file_item.stored_name)
        await self.file_repo.delete(session, file_item)

    async def download(
        self, session: AsyncSession, file_id: str
    ) -> tuple[StoredFile, Path]:
        """Resolve a file to its on-disk path for streaming, or 404."""
        file_item = await self.get_file(session, file_id)
        try:
            path = self.storage.path_for(file_item.stored_name)
        except StorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found",
            ) from exc
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored file not found",
            )
        return file_item, path
