from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import UpstreamUnavailableError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import RAGService

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        rag_service = RAGService()
        answer, pages = await rag_service.answer_query(document_id=req.document_id, query=req.query)
        return ChatResponse(answer=answer, source_pages=sorted(pages))
    except UpstreamUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "Upstream provider unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
