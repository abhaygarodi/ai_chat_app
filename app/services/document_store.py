from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from app.core.config import get_settings
from app.schemas.documents import DocumentMeta


_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


class DocumentStore:
    """
    Minimal JSON-backed store for uploaded document metadata.
    Intended for local/dev use and small deployments.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        _ensure_parent_dir(self._settings.DOCUMENTS_DB_PATH)
        os.makedirs(self._settings.UPLOAD_DIR, exist_ok=True)

    def _read_all(self) -> Dict[str, dict]:
        path = self._settings.DOCUMENTS_DB_PATH
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def _write_all(self, data: Dict[str, dict]) -> None:
        path = self._settings.DOCUMENTS_DB_PATH
        _ensure_parent_dir(path)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, path)

    def list_documents(self) -> List[DocumentMeta]:
        with _lock:
            data = self._read_all()
        metas: List[DocumentMeta] = []
        for raw in data.values():
            try:
                metas.append(DocumentMeta.model_validate(raw))
            except Exception:
                continue
        metas.sort(key=lambda m: m.created_at, reverse=True)
        return metas

    def get_document(self, document_id: UUID) -> Optional[DocumentMeta]:
        key = str(document_id)
        with _lock:
            data = self._read_all()
            raw = data.get(key)
        if not raw:
            return None
        try:
            return DocumentMeta.model_validate(raw)
        except Exception:
            return None

    def upsert_document(
        self,
        *,
        document_id: UUID,
        filename: str,
        size_bytes: int,
        page_count: int,
        tags: Optional[List[str]] = None,
    ) -> DocumentMeta:
        meta = DocumentMeta(
            document_id=document_id,
            filename=filename,
            size_bytes=size_bytes,
            page_count=page_count,
            created_at=_utc_now(),
            tags=list(tags or []),
            status="ready",
        )
        key = str(document_id)
        with _lock:
            data = self._read_all()
            data[key] = meta.model_dump(mode="json")
            self._write_all(data)
        return meta

    def delete_document(self, document_id: UUID) -> bool:
        key = str(document_id)
        with _lock:
            data = self._read_all()
            if key not in data:
                return False
            data.pop(key, None)
            self._write_all(data)
        return True

    def document_file_path(self, document_id: UUID) -> str:
        return os.path.join(self._settings.UPLOAD_DIR, f"{document_id}.pdf")

