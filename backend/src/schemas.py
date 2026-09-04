from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_name: str
    mime_type: str
    size: int
    processing_status: str
    scan_status: str | None
    scan_details: str | None
    metadata_json: dict | None
    requires_attention: bool
    created_at: datetime
    updated_at: datetime


class FileUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class UploadInitRequest(BaseModel):
    title: str
    original_name: str
    size: int = Field(gt=0)
    mime_type: str = "application/octet-stream"


class UploadInitResponse(BaseModel):
    file_id: str
    stored_name: str
    upload_id: str
    part_size: int
    num_parts: int


class PresignPartsRequest(BaseModel):
    part_numbers: list[int]


class PresignPartItem(BaseModel):
    part_number: int
    presigned_url: str


class UploadInfoResponse(BaseModel):
    file_id: str
    upload_id: str
    part_size: int
    num_parts: int
    uploaded_parts: list[int]


class AlertItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: str
    level: str
    message: str
    created_at: datetime
