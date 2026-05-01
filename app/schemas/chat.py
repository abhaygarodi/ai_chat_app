from __future__ import annotations

from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    document_id: UUID
    query: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    source_pages: List[int]

