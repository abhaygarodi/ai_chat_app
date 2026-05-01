from __future__ import annotations

import os
import tempfile
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import UpstreamUnavailableError
from app.schemas.upload import UploadResponse
from app.services.pdf_service import PDFService
from app.services.rag_service import RAGService

router = APIRouter()


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=415, detail="Only PDF files are supported")

    document_id: UUID = uuid4()

    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "")[1].lower()
        if suffix != ".pdf":
            suffix = ".pdf"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = tmp.name
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Empty file")
            tmp.write(content)

        pdf_service = PDFService()
        chunks = pdf_service.load_and_chunk_pdf(tmp_path, document_id=str(document_id))
        if not chunks:
            raise HTTPException(status_code=400, detail="No extractable text found in PDF")

        rag_service = RAGService()
        await rag_service.ingest_chunks(chunks)

        return UploadResponse(document_id=document_id, message="Upload successful")
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
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
