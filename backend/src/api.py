"""HTTP layer. Thin views that parse/validate requests, delegate to the
service layer, and shape responses. No business logic or storage/DB access."""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from starlette import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db import get_session
from src.repositories import AlertRepository, FileRepository
from src.schemas import AlertItem, FileItem, FileUpdate
from src.services import FileService
from src.storage import StorageService
from src.tasks import scan_file_for_threats

router = APIRouter()

# Application singletons: one storage service + one file service shared by all
# requests. Sessions are still per-request via the get_session dependency.
_file_service = FileService(
    storage=StorageService(settings.storage_dir),
    file_repo=FileRepository(),
    alert_repo=AlertRepository(),
)


@router.get("/files", response_model=list[FileItem])
async def list_files_view(session: AsyncSession = Depends(get_session)):
    return await _file_service.list_files(session)


@router.get("/alerts", response_model=list[AlertItem])
async def list_alerts_view(session: AsyncSession = Depends(get_session)):
    return await _file_service.list_alerts(session)


@router.post("/files", response_model=FileItem, status_code=status.HTTP_201_CREATED)
async def create_file_view(
    title: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    file_item = await _file_service.create_file(session, title=title, upload_file=file)
    scan_file_for_threats.delay(file_item.id)
    return file_item


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
    file_item, path = await _file_service.download(session, file_id)
    return FileResponse(
        path=path,
        media_type=file_item.mime_type,
        filename=file_item.original_name,
    )


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_view(
    file_id: str, session: AsyncSession = Depends(get_session)
):
    await _file_service.delete_file(session, file_id)
