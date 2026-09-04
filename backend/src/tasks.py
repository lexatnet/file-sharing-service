"""Celery worker: async file processing pipeline.

Three chained tasks:
    scan  ->  extract metadata  ->  send alert

Each task wraps its async body in ``asyncio.run()`` — a fresh event loop per
task. Because asyncpg connections are bound to the loop they were created on,
the worker must use a NullPool session factory (see ``src.db``), otherwise a
pooled connection reused across loops raises asyncpg's "another operation is
in progress". Storage is shared via ``src.storage``.
"""


import asyncio
import logging

from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db import worker_session_maker
from src.metadata import extract_metadata
from src.migration import run_migrations
from src.models import Alert, StoredFile
from src.repositories import FileRepository
from src.scanner import scan_file
from src.storage import StorageService

logger = logging.getLogger(__name__)


celery_app = Celery("file_tasks", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.on_after_configure.connect
def _initialize_database(**kwargs) -> None:
    """Apply pending migrations when the worker boots.



    The worker touches the DB on the first queued task, so it must not assume
    the API process already ran the migrations. Alembic is idempotent, making
    this safe even when both processes start simultaneously.



    """
    run_migrations()


async def requeue_incomplete(session: AsyncSession) -> int:
    """Re-dispatch the scanning chain for files whose processing never finished.



    Called on app startup: any file left in "uploaded" (the scan task was
    never picked up) or "processing" (the chain broke midway) is re-queued
    from its broken point, so "uploaded" files restart the whole scan while
    "processing" files only re-queue the metadata/alert tail. Returns the number
    of files requeued..



    """
    unfinished = await FileRepository().list_unfinished(session)
    for file_item in unfinished:
        if file_item.processing_status == "uploaded":
            scan_file_for_threats.delay(file_item.id)
        else:
            extract_file_metadata.delay(file_item.id)

    if unfinished:
        logger.info("Requeued %d incomplete file processing chain(s)", len(unfinished))
    return len(unfinished)


_storage = StorageService(settings.storage_dir)


async def _scan_file_for_threats(file_id: str) -> None:
    async with worker_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return

        result = scan_file(file_item.original_name, file_item.mime_type, file_item.size)

        file_item.processing_status = "processing"
        file_item.scan_status = result.status
        file_item.scan_details = result.details
        file_item.requires_attention = result.suspicious
        await session.commit()

    extract_file_metadata.delay(file_id)



async def _extract_file_metadata(file_id: str) -> None:
    async with worker_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return



        stored_path = _storage.path_for(file_item.stored_name)
        if not stored_path.exists():
            file_item.processing_status = "failed"
            file_item.scan_status = file_item.scan_status or "failed"
            file_item.scan_details = "stored file not found during metadata extraction"
            await session.commit()
            send_file_alert.delay(file_id)
            return



        file_item.metadata_json = extract_metadata(
            stored_path, file_item.original_name, file_item.mime_type, file_item.size
        )
        file_item.processing_status = "processed"
        await session.commit()

    send_file_alert.delay(file_id)


async def _send_file_alert(file_id: str) -> None:
    async with worker_session_maker() as session:
        file_item = await session.get(StoredFile, file_id)
        if not file_item:
            return



        if file_item.processing_status == "failed":
            alert = Alert(file_id=file_id, level="critical", message="File processing failed")
        elif file_item.requires_attention:
            alert = Alert(
                file_id=file_id,
                level="warning",
                message=f"File requires attention: {file_item.scan_details}",
            )
        else:
            alert = Alert(file_id=file_id, level="info", message="File processed successfully")

        session.add(alert)
        await session.commit()



@celery_app.task
def scan_file_for_threats(file_id: str) -> None:
    asyncio.run(_scan_file_for_threats(file_id))



@celery_app.task
def extract_file_metadata(file_id: str) -> None:
    asyncio.run(_extract_file_metadata(file_id))



@celery_app.task
def send_file_alert(file_id: str) -> None:
    asyncio.run(_send_file_alert(file_id))