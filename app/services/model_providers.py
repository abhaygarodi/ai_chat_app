from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass
from typing import Iterable, Protocol

from app.core.config import get_settings


class EmbeddingsProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class ChatProvider(Protocol):
    async def answer(self, *, context: str, question: str) -> str: ...


@dataclass(frozen=True)
class Providers:
    embeddings: EmbeddingsProvider
    chat: ChatProvider


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
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "me",
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


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


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


def _keywords(text: str) -> list[str]:
    out: list[str] = []
    for t in _tokens(text):
        if t in _STOPWORDS or len(t) < 3:
            continue
        out.append(_stem(t))
    return out


def _hash_embedding(text: str, *, dim: int) -> list[float]:
    vec = [0.0] * dim
    for tok in _tokens(text):
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = -1.0 if (h[4] & 1) else 1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        inv = 1.0 / norm
        vec = [v * inv for v in vec]
    return vec


class HashEmbeddingsProvider:
    def __init__(self) -> None:
        s = get_settings()
        if s.HASH_EMBEDDING_DIM < 64:
            raise ValueError("HASH_EMBEDDING_DIM must be >= 64")
        self._dim = s.HASH_EMBEDDING_DIM

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        def _do() -> list[list[float]]:
            return [_hash_embedding(t, dim=self._dim) for t in texts]

        return await asyncio.to_thread(_do)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(_hash_embedding, text, dim=self._dim)


class ExtractiveChatProvider:
    """
    No-LLM fallback that answers by extracting the most relevant sentence(s) from context.
    Returns "Not found in document" when it cannot confidently find an answer in context.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._min_score = float(s.EXTRACTIVE_MIN_SCORE)

    async def answer(self, *, context: str, question: str) -> str:
        ctx = (context or "").strip()
        q = (question or "").strip()
        if not ctx or not q:
            return "Not found in document"

        q_kw_list = _keywords(q)
        q_kw = set(q_kw_list)
        if not q_kw:
            return "Not found in document"
        required_overlap = 2 if len(q_kw) >= 2 else 1

        def _sentences(text: str) -> Iterable[str]:
            parts = re.split(r"(?<=[.!?])\s+|\n+", text)
            for p in parts:
                s = p.strip()
                if len(s) >= 20:
                    yield s

        best: list[tuple[float, str]] = []
        for sent in _sentences(ctx):
            s_kw = set(_keywords(sent))
            if not s_kw:
                continue
            overlap = len(q_kw & s_kw)
            if overlap < required_overlap:
                continue
            overlap_ratio = overlap / max(1, len(q_kw))
            score = overlap_ratio
            best.append((score, sent))

        if not best:
            return "Not found in document"

        best.sort(key=lambda x: x[0], reverse=True)
        top_score = best[0][0]
        if top_score < self._min_score:
            return "Not found in document"

        # Return up to 2 supporting sentences, verbatim from context.
        chosen = [best[0][1]]
        for score, sent in best[1:]:
            if len(chosen) >= 2:
                break
            if sent not in chosen and score >= top_score * 0.85:
                chosen.append(sent)
        return "\n".join(chosen).strip() or "Not found in document"


class GroqChatProvider:
    """
    Cloud LLM via Groq's OpenAI-compatible Chat Completions API.
    Sends a strict-RAG prompt and returns the model's text answer.
    """

    _ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    _SYSTEM = (
        "You are a strict document QA assistant. "
        "Answer the user's question using ONLY the provided context. "
        "Each context chunk is prefixed with its page number, like [page 2]. "
        "After your answer, cite the page(s) you used as [page N] tokens (e.g. [page 2] or [page 2] [page 4]). "
        "Cite ONLY the pages whose content you actually used. "
        'If the answer cannot be found in the context, output exactly: "Not found in document" with no page tags. '
        "Do not use outside knowledge. Keep answers concise."
    )

    def __init__(self) -> None:
        s = get_settings()
        if not s.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set. Add it to .env to use LLM_PROVIDER=groq.")
        self._api_key = s.GROQ_API_KEY
        self._model = s.GROQ_MODEL
        self._timeout = s.GROQ_TIMEOUT
        self._temperature = s.GROQ_TEMPERATURE

    async def answer(self, *, context: str, question: str) -> str:
        import httpx

        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": self._SYSTEM},
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        try:
            return (data["choices"][0]["message"]["content"] or "").strip() or "Not found in document"
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Groq response shape: {data}") from exc


def get_providers(*, prompt) -> Providers:
    s = get_settings()

    if s.EMBEDDINGS_PROVIDER == "hash":
        embeddings = HashEmbeddingsProvider()
    else:
        raise ValueError('Unsupported EMBEDDINGS_PROVIDER. Use "hash".')

    if s.LLM_PROVIDER == "extractive":
        chat = ExtractiveChatProvider()
    elif s.LLM_PROVIDER == "groq":
        chat = GroqChatProvider()
    else:
        raise ValueError('Unsupported LLM_PROVIDER. Use "extractive" or "groq".')

    return Providers(embeddings=embeddings, chat=chat)
