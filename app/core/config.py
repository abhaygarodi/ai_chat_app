from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "PDF RAG Chat API"
    CORS_ALLOW_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # Providers (free/offline)
    # - LLM_PROVIDER: "extractive"
    # - EMBEDDINGS_PROVIDER: "hash"
    LLM_PROVIDER: str = "extractive"
    EMBEDDINGS_PROVIDER: str = "hash"


    QDRANT_PATH: str = "./qdrant_data"
    QDRANT_COLLECTION: str = "pdf_chunks"
    QDRANT_RECREATE_ON_DIM_MISMATCH: bool = True

    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150

    TOP_K: int = 4
    MAX_CONTEXT_CHARS: int = 12000

    # Hash embeddings (used when EMBEDDINGS_PROVIDER == "hash")
    HASH_EMBEDDING_DIM: int = 1024

    # Extractive answering (used when LLM_PROVIDER == "extractive")
    EXTRACTIVE_MIN_SCORE: float = 0.12
    EXTRACTIVE_MAX_CHUNKS_SCAN: int = 400

    # Groq (used when LLM_PROVIDER == "groq")
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_TIMEOUT: float = 30.0
    GROQ_TEMPERATURE: float = 0.0

    # OCR (for scanned/image-only PDFs)
    ENABLE_OCR: bool = True
    OCR_LANG: str = "eng"
    OCR_DPI: int = 200
    OCR_MIN_TEXT_CHARS: int = 30
    # Windows example: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
    TESSERACT_CMD: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
