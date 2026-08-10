"""File upload/response schemas."""

from pydantic import BaseModel, ConfigDict


class FileUploadResponse(BaseModel):
    file_id: str
    name: str
    size: int
    content_type: str
    bucket: str
    key: str
    created_at: str


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    name: str
    size: int
    content_type: str
    bucket: str
    key: str
    created_at: str
    download_url: str | None = None


class FileDeletedResponse(BaseModel):
    file_id: str
    deleted: bool = True


class FileListOut(BaseModel):
    files: list[FileOut]
    count: int
