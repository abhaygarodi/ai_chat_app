from __future__ import annotations

import os
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.schemas.documents import DocumentListResponse, DocumentMeta
from app.services.document_store import DocumentStore


router = APIRouter()


@router.get("/documents", response_model=DocumentListResponse, status_code=status.HTTP_200_OK)
def list_documents() -> DocumentListResponse:
    store = DocumentStore()
    docs = store.list_documents()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.get("/documents/{document_id}", response_model=DocumentMeta, status_code=status.HTTP_200_OK)
def get_document(document_id: UUID) -> DocumentMeta:
    store = DocumentStore()
    doc = store.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get(
    "/documents/{document_id}/file",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
)
def get_document_file(document_id: UUID) -> FileResponse:
    store = DocumentStore()
    doc = store.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = store.document_file_path(document_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Document file not found")

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=doc.filename,
    )

