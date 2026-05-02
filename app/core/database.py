from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import get_settings


@dataclass(frozen=True)
class QdrantDeps:
    client: QdrantClient
    collection_name: str


_deps: Optional[QdrantDeps] = None


def get_qdrant() -> QdrantDeps:
    global _deps
    if _deps is not None:
        return _deps

    settings = get_settings()
    if settings.QDRANT_URL:
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
            prefer_grpc=False,
        )
    else:
        client = QdrantClient(path=settings.QDRANT_PATH)
    _deps = QdrantDeps(client=client, collection_name=settings.QDRANT_COLLECTION)
    return _deps


def close_qdrant() -> None:
    global _deps
    if _deps is None:
        return
    try:
        _deps.client.close()
    except Exception:
        pass
    _deps = None


def collection_exists() -> bool:
    deps = get_qdrant()
    existing = deps.client.get_collections().collections
    return any(c.name == deps.collection_name for c in existing)


def _ensure_payload_indexes(client: QdrantClient, name: str) -> None:
    """
    Qdrant Cloud requires explicit payload indexes before you can filter by a field.
    Local file-based Qdrant doesn't enforce this. Idempotent — safe to call repeatedly.
    """
    for field, schema in (("document_id", qm.PayloadSchemaType.KEYWORD),):
        try:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            # Index already exists or backend doesn't require it — safe to ignore.
            pass


def ensure_collection(vector_size: int) -> None:
    deps = get_qdrant()
    client = deps.client
    name = deps.collection_name
    settings = get_settings()

    existing = client.get_collections().collections
    if any(c.name == name for c in existing):
        info = client.get_collection(name)
        existing_size = info.config.params.vectors.size  # type: ignore[union-attr]
        if existing_size != vector_size:
            if settings.QDRANT_RECREATE_ON_DIM_MISMATCH:
                client.delete_collection(collection_name=name)
            else:
                raise ValueError(
                    f"Qdrant collection '{name}' has vector size {existing_size}, "
                    f"but embeddings have size {vector_size}. "
                    "Delete your Qdrant data directory or enable QDRANT_RECREATE_ON_DIM_MISMATCH."
                )
        else:
            _ensure_payload_indexes(client, name)
            return

    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
    )
    _ensure_payload_indexes(client, name)
