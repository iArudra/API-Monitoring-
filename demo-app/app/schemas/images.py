"""Image processing response schema."""

from pydantic import BaseModel


class ImageProcessResponse(BaseModel):
    status: str
    processing_id: str
    bucket: str
    key: str
    size_bytes: int
    notification: str
