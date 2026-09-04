"""Data-access layer. Each repository owns the queries for one aggregate;
sessions are injected by the caller (service layer), so repositories stay
plain and dependency-free."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Alert, StoredFile


class FileRepository:
    async def list_all(self, session: AsyncSession) -> list[StoredFile]:
        result = await session.execute(
            select(StoredFile).order_by(StoredFile.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_unfinished(self, session: AsyncSession) -> list[StoredFile]:
        """Files whose processing chain did not finish (requeued on startup)."""
        result = await session.execute(
            select(StoredFile).where(
                StoredFile.processing_status.in_(["uploaded", "processing"]),
            )
        )
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, file_id: str) -> StoredFile | None:
        return await session.get(StoredFile, file_id)

    async def create(
        self,
        session: AsyncSession,
        *,
        id: str,
        title: str,
        original_name: str,
        stored_name: str,
        mime_type: str,
        size: int,
        processing_status: str = "uploaded",
        upload_id: str | None = None,
    ) -> StoredFile:
        file_item = StoredFile(
            id=id,
            title=title,
            original_name=original_name,
            stored_name=stored_name,
            mime_type=mime_type,
            size=size,
            processing_status=processing_status,
            upload_id=upload_id,
        )
        session.add(file_item)
        await session.commit()
        await session.refresh(file_item)
        return file_item

    async def update_title(
        self, session: AsyncSession, file_item: StoredFile, title: str
    ) -> StoredFile:
        file_item.title = title
        await session.commit()
        await session.refresh(file_item)
        return file_item

    async def delete(self, session: AsyncSession, file_item: StoredFile) -> None:
        # Alerts referencing this file are removed by the FK ON DELETE CASCADE.
        await session.delete(file_item)
        await session.commit()


class AlertRepository:
    async def list_all(self, session: AsyncSession) -> list[Alert]:
        result = await session.execute(
            select(Alert).order_by(Alert.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        file_id: str,
        level: str,
        message: str,
    ) -> Alert:
        alert = Alert(file_id=file_id, level=level, message=message)
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert
