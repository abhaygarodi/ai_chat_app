from __future__ import annotations

import math
import re
import uuid
from typing import List, Sequence, Set, Tuple

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from qdrant_client.http import models as qm

from app.core.config import get_settings
from app.core.database import (
    _ensure_payload_indexes,
    collection_exists,
    ensure_collection,
    get_qdrant,
)
from app.core.exceptions import UpstreamUnavailableError
from app.schemas.chat import Citation
from app.services.model_providers import ExtractiveChatProvider, Providers, get_providers


def _short_quote(text: str, *, limit: int = 280) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "might",
    "more",
    "most",
    "not",
    "of",
    "on",
    "or",
    "our",
    "out",
    "please",
    "should",
    "so",
    "some",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "us",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
    # Generic query words that often hurt extractive matching quality
    "name",
    "names",
    "policy",
    "policies",
}


def _stem(token: str) -> str:
    t = (token or "").lower()
    if len(t) <= 3:
        return t
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    for suf in ("ing", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def _keyword_set(text: str) -> Set[str]:
    return {
        _stem(m.group(0))
        for m in _WORD_RE.finditer(text or "")
        if m.group(0) and m.group(0).lower() not in _STOPWORDS and len(m.group(0)) >= 3
    }


def _overlap_score(query_tokens: Set[str], text: str) -> float:
    tokens = _keyword_set(text)
    if not tokens:
        return 0.0
    overlap = len(query_tokens & tokens)
    # Need a minimum amount of coverage of the question keywords.
    # For short queries (<=2 keywords) require at least 2 overlaps when possible to reduce false positives,
    # but allow 1 overlap if the query only has 1 keyword after filtering.
    required_overlap = 2 if len(query_tokens) >= 2 else 1
    if overlap < required_overlap:
        return 0.0
    return overlap / max(1, len(query_tokens))


class RAGService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a strict document QA assistant.\n"
                    "Answer the user's question using ONLY the provided context.\n"
                    'If the answer cannot be found in the context, output exactly: "Not found in document"\n'
                    "Do not use outside knowledge.",
                ),
                ("human", "Context:\n{context}\n\nQuestion: {question}"),
            ]
        )
        self._providers: Providers = get_providers(prompt=self._prompt)

    async def ingest_chunks(self, chunks: Sequence[Document]) -> None:
        if not chunks:
            return

        texts = [c.page_content for c in chunks]
        try:
            vectors = await self._providers.embeddings.embed_documents(texts)
        except Exception as exc:
            raise UpstreamUnavailableError(str(exc)) from exc
        if not vectors or not vectors[0]:
            raise ValueError("Failed to create embeddings for document chunks")

        ensure_collection(vector_size=len(vectors[0]))
        deps = get_qdrant()

        points: List[qm.PointStruct] = []
        for doc, vector in zip(chunks, vectors):
            document_id = doc.metadata.get("document_id")
            page_number = doc.metadata.get("page_number")
            if not document_id:
                raise ValueError("Chunk missing required metadata: document_id")
            if page_number is None:
                raise ValueError("Chunk missing required metadata: page_number")

            payload = {
                "document_id": str(document_id),
                "page_number": int(page_number),
                "text": doc.page_content,
                "chunk_index": int(doc.metadata.get("chunk_index", 0)),
            }
            points.append(
                qm.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload,
                )
            )

        deps.client.upsert(collection_name=deps.collection_name, points=points)

    async def answer_query(
        self, document_id: uuid.UUID, query: str
    ) -> Tuple[str, Set[int], List[Citation]]:
        query = (query or "").strip()
        if not query:
            raise ValueError("Query cannot be empty")

        if not collection_exists():
            return "Not found in document", set(), []

        deps = get_qdrant()
        # Idempotent: ensures the document_id payload index exists on the
        # already-created collection (required by Qdrant Cloud for filtering).
        _ensure_payload_indexes(deps.client, deps.collection_name)
        doc_filter = qm.Filter(
            must=[
                qm.FieldCondition(
                    key="document_id",
                    match=qm.MatchValue(value=str(document_id)),
                )
            ]
        )

        contexts: List[str] = []
        pages: Set[int] = set()
        retrieved_pages: List[int] = []
        raw_contexts: List[str] = []
        chunk_texts_pages: List[Tuple[str, int | None]] = []

        if self._settings.LLM_PROVIDER == "extractive":
            q_tokens = _keyword_set(query)
            if not q_tokens:
                return "Not found in document", set(), []

            scanned = 0
            offset = None
            scored: list[tuple[float, str, int | None]] = []
            while scanned < self._settings.EXTRACTIVE_MAX_CHUNKS_SCAN:
                batch, offset = deps.client.scroll(
                    collection_name=deps.collection_name,
                    scroll_filter=doc_filter,
                    limit=min(128, self._settings.EXTRACTIVE_MAX_CHUNKS_SCAN - scanned),
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not batch:
                    break
                scanned += len(batch)

                for rec in batch:
                    payload = rec.payload or {}
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        continue
                    score = _overlap_score(q_tokens, text)
                    if score <= 0:
                        continue
                    page_number = payload.get("page_number")
                    scored.append((score, text, int(page_number) if page_number is not None else None))

                if offset is None:
                    break

            if not scored:
                return "Not found in document", set(), []

            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[: self._settings.TOP_K]
            contexts = [t[1] for t in top]
            for _, text, pg in top:
                if pg is not None:
                    pages.add(pg)
                chunk_texts_pages.append((text, pg))
                raw_contexts.append(text)
        else:
            try:
                vector = await self._providers.embeddings.embed_query(query)
            except Exception as exc:
                raise UpstreamUnavailableError(str(exc)) from exc
            if not vector:
                raise ValueError("Failed to embed query")

            resp = deps.client.query_points(
                collection_name=deps.collection_name,
                query=vector,
                limit=self._settings.TOP_K,
                query_filter=doc_filter,
                with_payload=True,
            )

            chunk_pages: list[int | None] = []
            for r in resp.points:
                payload = r.payload or {}
                text = str(payload.get("text", "")).strip()
                if not text:
                    continue
                page_number = payload.get("page_number")
                pg = int(page_number) if page_number is not None else None
                chunk_pages.append(pg)
                if pg is not None:
                    retrieved_pages.append(pg)
                raw_contexts.append(text)
                chunk_texts_pages.append((text, pg))
                # Tag each chunk with its page so the LLM can cite sources accurately.
                tag = f"[page {pg}]" if pg is not None else "[page ?]"
                contexts.append(f"{tag}\n{text}")

        context_text = "\n\n---\n\n".join(contexts)
        context_text = context_text[: self._settings.MAX_CONTEXT_CHARS]

        if not context_text.strip():
            return "Not found in document", set(), []

        used_fallback = False
        try:
            answer = await self._providers.chat.answer(context=context_text, question=query)
        except Exception:
            if self._settings.LLM_PROVIDER == "extractive":
                raise
            # Primary LLM unavailable (e.g. bad API key, network outage).
            # Fall back to the offline extractive provider over the raw retrieved context
            # so the system still produces grounded answers.
            fallback = ExtractiveChatProvider()
            fallback_ctx = "\n\n---\n\n".join(raw_contexts)[: self._settings.MAX_CONTEXT_CHARS]
            answer = await fallback.answer(context=fallback_ctx, question=query)
            used_fallback = True

        if self._settings.LLM_PROVIDER != "extractive" and not used_fallback:
            cited = {int(m) for m in re.findall(r"\[page\s+(\d+)\]", answer or "", flags=re.IGNORECASE)}
            answer = re.sub(r"\s*\[page\s+\d+\]", "", answer or "", flags=re.IGNORECASE).strip()
            pages = cited
            if "not found in document" in answer.lower():
                pages = set()
        elif used_fallback:
            if "not found in document" not in (answer or "").lower():
                # Attribute each answer sentence to the chunk(s) whose text contains it,
                # so we cite only the page(s) the answer actually came from.
                cited: Set[int] = set()
                for line in (answer or "").splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    for text, pg in chunk_texts_pages:
                        if pg is not None and s in text:
                            cited.add(pg)
                pages = cited

        # Build per-page citations: pick the chunk text most relevant to the answer.
        citations: List[Citation] = []
        if pages and "not found in document" not in (answer or "").lower():
            answer_lines = [ln.strip() for ln in (answer or "").splitlines() if ln.strip()]
            for pg in sorted(pages):
                best_text: str | None = None
                for text, p in chunk_texts_pages:
                    if p != pg:
                        continue
                    if any(ln and ln in text for ln in answer_lines):
                        best_text = text
                        break
                if best_text is None:
                    for text, p in chunk_texts_pages:
                        if p == pg:
                            best_text = text
                            break
                if best_text:
                    citations.append(Citation(page=pg, quote=_short_quote(best_text)))

        return answer, pages, citations
