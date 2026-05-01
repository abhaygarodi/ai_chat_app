from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import chat, ui, upload
from app.core.config import get_settings
from app.core.database import close_qdrant


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.APP_NAME)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(upload.router, tags=["upload"])
    app.include_router(chat.router, tags=["chat"])
    app.include_router(ui.router, tags=["ui"])

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"status": "ok", "docs": "/docs"}

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    def _shutdown() -> None:
        close_qdrant()

    return app


app = create_app()
