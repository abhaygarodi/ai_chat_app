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
            return

    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
    )
