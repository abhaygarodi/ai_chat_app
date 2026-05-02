from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: UUID
    message: str
    filename: str | None = None
    size_bytes: int | None = None
    page_count: int | None = None
