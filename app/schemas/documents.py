from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentMeta(BaseModel):
    document_id: UUID
    filename: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(ge=0)
    page_count: int = Field(ge=0)
    created_at: datetime
    tags: List[str] = Field(default_factory=list)
    status: str = Field(default="ready")


class DocumentListResponse(BaseModel):
    documents: List[DocumentMeta]
    total: int


class DocumentCreateMeta(BaseModel):
    tags: Optional[List[str]] = None

