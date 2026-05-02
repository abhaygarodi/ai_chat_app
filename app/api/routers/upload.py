from __future__ import annotations

import os
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import UpstreamUnavailableError
from app.schemas.upload import UploadResponse
from app.services.document_store import DocumentStore
from app.services.pdf_service import PDFService
from app.services.rag_service import RAGService

router = APIRouter()


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=415, detail="Only PDF files are supported")

    document_id: UUID = uuid4()

    store = DocumentStore()
    saved_path = store.document_file_path(document_id)
    filename = os.path.basename(file.filename or "") or f"{document_id}.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        os.makedirs(os.path.dirname(saved_path), exist_ok=True)
        with open(saved_path, "wb") as f:
            f.write(content)

        try:
            import fitz  # pymupdf

            with fitz.open(saved_path) as doc:
                page_count = int(doc.page_count or 0)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid PDF: {exc}") from exc

        pdf_service = PDFService()
        chunks = pdf_service.load_and_chunk_pdf(saved_path, document_id=str(document_id))
        if not chunks:
            raise HTTPException(status_code=400, detail="No extractable text found in PDF")

        rag_service = RAGService()
        await rag_service.ingest_chunks(chunks)

        meta = store.upsert_document(
            document_id=document_id,
            filename=filename,
            size_bytes=len(content),
            page_count=page_count,
            tags=None,
        )

        return UploadResponse(
            document_id=document_id,
            message="Upload successful",
            filename=meta.filename,
            size_bytes=meta.size_bytes,
            page_count=meta.page_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "Upstream provider unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc
    finally:
        try:
            if os.path.exists(saved_path):
                # If we didn't successfully store metadata, treat this upload as failed and clean up the file.
                doc = store.get_document(document_id)
                if not doc:
                    os.remove(saved_path)
        except Exception:
            pass
