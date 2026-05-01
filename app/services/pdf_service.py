from __future__ import annotations

from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings


class PDFService:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", " ", ""],
        )

    def _ocr_page_text(self, file_path: str, page_number: int) -> str:
        """
        OCR a 1-based page number using PyMuPDF rendering + Tesseract.
        Requires external Tesseract installation.
        """
        try:
            import fitz  # pymupdf
            import pytesseract
            from PIL import Image
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "OCR dependencies missing. Install pymupdf, pillow, pytesseract."
            ) from exc

        if self._settings.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = self._settings.TESSERACT_CMD

        with fitz.open(file_path) as doc:
            if page_number < 1 or page_number > doc.page_count:
                return ""
            page = doc.load_page(page_number - 1)
            zoom = max(1.0, float(self._settings.OCR_DPI) / 72.0)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            text = pytesseract.image_to_string(img, lang=self._settings.OCR_LANG)
            return (text or "").strip()

    def load_and_chunk_pdf(self, file_path: str, document_id: str) -> List[Document]:
        loader = PyPDFLoader(file_path)
        pages = loader.load()

        normalized_pages: List[Document] = []
        for doc in pages:
            page_index = doc.metadata.get("page")
            page_number = int(page_index) + 1 if page_index is not None else 1
            text = (doc.page_content or "").strip()

            # Hybrid extraction: if selectable text is missing/too short, OCR this page (if enabled).
            if self._settings.ENABLE_OCR and len(text) < self._settings.OCR_MIN_TEXT_CHARS:
                ocr_text = ""
                try:
                    ocr_text = self._ocr_page_text(file_path, page_number=page_number)
                except Exception:
                    ocr_text = ""
                if ocr_text and len(ocr_text) > len(text):
                    text = ocr_text

            if not text:
                continue
            normalized_pages.append(
                Document(
                    page_content=text,
                    metadata={
                        "document_id": document_id,
                        "page_number": page_number,
                    },
                )
            )

        chunks = self._splitter.split_documents(normalized_pages)
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
        return chunks
