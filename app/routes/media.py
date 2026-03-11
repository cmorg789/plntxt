import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_agent_or_admin
from app.config import settings
from app.db import get_db
from app.models.media import Media
from app.models.user import User

router = APIRouter(prefix="/media", tags=["media"])

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class MediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    post_id: UUID | None
    filename: str
    mime_type: str
    alt_text: str | None
    storage_path: str
    size_bytes: int
    created_at: datetime


@router.post("", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    post_id: UUID | None = Form(None),
    alt_text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_agent_or_admin),
):
    # Read file contents
    contents = await file.read()

    # Validate file size
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB.",
        )

    # Validate mime type
    mime_type = file.content_type or ""
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{mime_type}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # Generate unique filename
    original_filename = file.filename or "upload"
    unique_filename = f"{uuid.uuid4()}_{original_filename}"

    # Ensure storage directory exists
    storage_dir = Path(settings.MEDIA_STORAGE_PATH)
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Write file to disk
    file_path = storage_dir / unique_filename
    file_path.write_bytes(contents)

    # Create database record
    media = Media(
        post_id=post_id,
        filename=unique_filename,
        mime_type=mime_type,
        alt_text=alt_text,
        storage_path=str(file_path),
        size_bytes=len(contents),
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    return media


@router.get("/{filename}", response_class=FileResponse)
async def get_media(
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    file_path = Path(settings.MEDIA_STORAGE_PATH) / filename

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        )

    # Try to get content type from the database record
    result = await db.execute(select(Media).where(Media.filename == filename))
    media = result.scalar_one_or_none()

    if media:
        content_type = media.mime_type
    else:
        content_type, _ = mimetypes.guess_type(filename)
        content_type = content_type or "application/octet-stream"

    return FileResponse(file_path, media_type=content_type)
