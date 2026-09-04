"""HTTP layer. Thin views that parse/validate requests, delegate to the
service layer, and shape responses. No business logic or storage/DB access."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db import get_session
from src.repositories import AlertRepository, FileRepository
from src.schemas import (
    AlertItem,
    FileItem,
    FileUpdate,
    PresignPartItem,
    PresignPartsRequest,
    UploadInfoResponse,
    UploadInitRequest,
    UploadInitResponse,
)
from src.events import publish_event, stream_event_source
from src.services import FileService
from src.storage import S3StorageService
from src.tasks import scan_file_for_threats

router = APIRouter()

# Application singletons: one storage service + one file service shared by all
# requests. Sessions are still per-request via the get_session dependency.
_file_service = FileService(
    storage=S3StorageService(settings),
    file_repo=FileRepository(),
    alert_repo=AlertRepository(),
)


@router.get("/files", response_model=list[FileItem])
async def list_files_view(session: AsyncSession = Depends(get_session)):
    return await _file_service.list_files(session)


@router.get("/alerts", response_model=list[AlertItem])
async def list_alerts_view(session: AsyncSession = Depends(get_session)):
    return await _file_service.list_alerts(session)


# --- chunked resumable upload (client uploads parts directly to S3) ---------


@router.post(
    "/files/uploads", response_model=UploadInitResponse, status_code=status.HTTP_201_CREATED
)
async def initiate_upload_view(
    payload: UploadInitRequest, session: AsyncSession = Depends(get_session)
):
    return await _file_service.initiate_upload(
        session,
        title=payload.title,
        original_name=payload.original_name,
        size=payload.size,
        mime_type=payload.mime_type,
    )


@router.get("/files/uploads/{file_id}", response_model=UploadInfoResponse)
async def resume_upload_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    """Upload info for resuming: which chunks are already in S3."""
    return await _file_service.resume_upload(session, file_id)


@router.post(
    "/files/uploads/{file_id}/presign", response_model=list[PresignPartItem]
)
async def presign_parts_view(
    file_id: str,
    payload: PresignPartsRequest,
    session: AsyncSession = Depends(get_session),
):
    return await _file_service.presign_parts(session, file_id, payload.part_numbers)


@router.post(
    "/files/uploads/{file_id}/complete", response_model=FileItem
)
async def complete_upload_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    file_item = await _file_service.complete_upload(session, file_id)
    scan_file_for_threats.delay(file_item.id)
    # A new file just appeared in the list — notify connected clients.
    await publish_event("file_created", file_item.id)
    return file_item


@router.delete("/files/uploads/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def abort_upload_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    await _file_service.abort_upload(session, file_id)


@router.get("/events")
async def events_view(request: Request):
    """SSE stream: relays file-processing events from the worker to the browser."""
    return StreamingResponse(
        stream_event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- file CRUD ---------------------------------------------------------------


@router.get("/files/{file_id}", response_model=FileItem)
async def get_file_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    return await _file_service.get_file(session, file_id)


@router.patch("/files/{file_id}", response_model=FileItem)
async def update_file_view(
    file_id: str,
    payload: FileUpdate,
    session: AsyncSession = Depends(get_session),
):
    return await _file_service.update_file(session, file_id=file_id, title=payload.title)


@router.get("/files/{file_id}/download")
async def download_file_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    file_item, body = await _file_service.download(session, file_id)
    return StreamingResponse(
        body.stream,
        media_type=file_item.mime_type,
        headers={"Content-Disposition": FileService.download_name(file_item)},
    )


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    await _file_service.delete_file(session, file_id)