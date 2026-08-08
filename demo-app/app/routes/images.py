"""Image processing route (S3 -> Lambda -> SNS distributed workflow)."""

import asyncio

from fastapi import APIRouter, Depends, File, UploadFile

from ..deps import get_container, require_auth
from ..schemas.images import ImageProcessResponse
from ..services import Container

router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_auth)])


@router.post("/process", response_model=ImageProcessResponse, summary="Process an image (S3 -> Lambda -> SNS)")
async def process_image(
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
) -> ImageProcessResponse:
    content = await file.read()
    # Blocking boto3 calls (incl. the Lambda invoke) must not run on the event loop.
    return await asyncio.to_thread(
        container.lambda_service.process_image,
        file.filename or "image.bin",
        content,
        file.content_type,
    )
