from app.api.routers.chat import router as chat_router
from app.api.routers.documents import router as documents_router
from app.api.routers.ui import router as ui_router
from app.api.routers.upload import router as upload_router

__all__ = ["chat_router", "documents_router", "upload_router", "ui_router"]
