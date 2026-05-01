# PDF RAG Chat App

A FastAPI backend that lets you **upload a PDF and ask questions about its content**. It answers using only the PDF's text and cites the source page numbers. If the answer isn't in the document, it explicitly returns `"Not found in document"`.

---

## Features

- **PDF upload** with automatic text extraction
- **OCR fallback** for scanned / image-only PDFs (Tesseract)
- **Chunking** with LangChain's recursive splitter
- **Vector storage** via Qdrant (local, file-backed)
- **Retrieval-Augmented Generation (RAG)** with top-K cosine search filtered by `document_id`
- **LLM answers** via Groq (free tier, `llama-3.1-8b-instant`)
- **Strict grounding** — answers come only from the uploaded PDF
- **Page citations** — every answer reports which page(s) it came from
- **Pluggable providers** — swap LLM / embeddings via `.env`
- **Browser test UI** at `/ui`
- **Auto-generated Swagger docs** at `/docs`

---

## Architecture

```
                ┌─────────────┐
   Upload PDF ──▶  /upload    │
                │             │
                │  PyPDFLoader│
                │     │       │
                │     ▼       │
                │  OCR fallback (if page text < 30 chars)
                │     │       │
                │     ▼       │
                │  RecursiveCharacterTextSplitter
                │     │       │
                │     ▼       │
                │  HashEmbeddings (1024-dim)
                │     │       │
                │     ▼       │
                │  Qdrant.upsert(document_id, page_number, text)
                └─────────────┘

                ┌─────────────┐
    Question ──▶│  /chat      │
                │             │
                │  HashEmbeddings(query)
                │     │       │
                │     ▼       │
                │  Qdrant.query_points (filter: document_id)
                │     │       │
                │     ▼       │
                │  Tag chunks as [page N]
                │     │       │
                │     ▼       │
                │  Groq LLM (strict-RAG prompt + page citations)
                │     │       │
                │     ▼       │
                │  Parse [page N] tokens → source_pages
                └─────────────┘
                       │
                       ▼
              { "answer": "...", "source_pages": [2] }
```

---

## Tech Stack

| Component | Library / Service | Where it lives |
|---|---|---|
| Web framework | FastAPI + Uvicorn | [app/main.py](app/main.py) |
| PDF extraction | LangChain `PyPDFLoader` (pypdf) | [app/services/pdf_service.py](app/services/pdf_service.py) |
| OCR | PyMuPDF + Pillow + pytesseract | [app/services/pdf_service.py](app/services/pdf_service.py) |
| Chunking | LangChain `RecursiveCharacterTextSplitter` | [app/services/pdf_service.py](app/services/pdf_service.py) |
| Embeddings | Custom hash-based (no model download) | [app/services/model_providers.py](app/services/model_providers.py) |
| Vector store | Qdrant (local persistent) | [app/core/database.py](app/core/database.py) |
| Retrieval | Qdrant `query_points` + payload filter | [app/services/rag_service.py](app/services/rag_service.py) |
| LLM | Groq (`llama-3.1-8b-instant`) | [app/services/model_providers.py](app/services/model_providers.py) |
| HTTP client | httpx (async) | [app/services/model_providers.py](app/services/model_providers.py) |
| Config | Pydantic Settings + `.env` | [app/core/config.py](app/core/config.py) |
| Test UI | Static HTML page | [app/api/routers/ui.py](app/api/routers/ui.py) |

---

## Project Layout

```
RAG_chat_app/
├── app/
│   ├── main.py                       # FastAPI app factory + lifecycle
│   ├── api/
│   │   └── routers/
│   │       ├── upload.py             # POST /upload
│   │       ├── chat.py               # POST /chat
│   │       └── ui.py                 # GET  /ui (test page)
│   ├── core/
│   │   ├── config.py                 # Pydantic settings (env-driven)
│   │   ├── database.py               # Qdrant client singleton
│   │   └── exceptions.py             # UpstreamUnavailableError
│   ├── schemas/
│   │   ├── upload.py                 # UploadResponse model
│   │   └── chat.py                   # ChatRequest / ChatResponse models
│   └── services/
│       ├── pdf_service.py            # PDF → chunks (with OCR fallback)
│       ├── rag_service.py            # ingest + retrieve + answer
│       └── model_providers.py        # Embeddings + LLM provider classes
├── qdrant_data/                      # Local Qdrant data (auto-created)
├── .env                              # Provider config + API keys
├── requirements.txt
└── README.md
```

---

## API Reference

### `POST /upload`
Upload a PDF for ingestion.

**Request** (multipart/form-data):
- `file` — PDF file

**Response** `201 Created`:
```json
{
  "document_id": "751b2f23-f957-4f7b-a020-0cc577bef489",
  "message": "Upload successful"
}
```

**Errors:**
- `400` — empty file or no extractable text
- `415` — non-PDF content type
- `503` — embedding/LLM provider unavailable

---

### `POST /chat`
Ask a question about a previously uploaded PDF.

**Request** (application/json):
```json
{
  "document_id": "751b2f23-f957-4f7b-a020-0cc577bef489",
  "query": "How many days of PTO do full-time employees get?"
}
```

**Response** `200 OK`:
```json
{
  "answer": "22 days of Paid Time Off (PTO) per calendar year.",
  "source_pages": [2]
}
```

**Out-of-document behavior:**
```json
{
  "answer": "Not found in document",
  "source_pages": []
}
```

---

### `GET /healthz`
Liveness probe → `{"status":"ok"}`

### `GET /ui`
Browser test page for upload + chat.

### `GET /docs`
Auto-generated Swagger UI.

---

## Setup

### 1. Install dependencies
```powershell
pip install -r requirements.txt
```

### 2. (Optional) Install Tesseract for OCR
Required only for scanned/image-only PDFs. Download from
[github.com/UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki),
then set in `.env`:
```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### 3. Get a free Groq API key
Sign up at [console.groq.com](https://console.groq.com), create a key, and put it in `.env`:
```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

### 4. Run
```powershell
python -m uvicorn app.main:app --reload
```

Open:
- **Test UI** → http://127.0.0.1:8000/ui
- **Swagger** → http://127.0.0.1:8000/docs

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` (cloud LLM) or `extractive` (no-LLM offline) |
| `EMBEDDINGS_PROVIDER` | `hash` | Hash-based embeddings (no model download) |
| `HASH_EMBEDDING_DIM` | `1024` | Embedding vector dimension |
| `GROQ_API_KEY` | _(required)_ | Your Groq API key |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq chat model |
| `GROQ_TIMEOUT` | `30` | HTTP timeout (seconds) |
| `GROQ_TEMPERATURE` | `0.0` | Sampling temperature |
| `QDRANT_PATH` | `./qdrant_data` | Local Qdrant data dir |
| `QDRANT_COLLECTION` | `pdf_chunks` | Collection name |
| `QDRANT_RECREATE_ON_DIM_MISMATCH` | `true` | Wipe collection on dim change |
| `CHUNK_SIZE` | `1000` | Chunk size (chars) |
| `CHUNK_OVERLAP` | `150` | Chunk overlap (chars) |
| `TOP_K` | `4` | Top-K retrieval |
| `MAX_CONTEXT_CHARS` | `12000` | Max chars sent to LLM |
| `ENABLE_OCR` | `true` | OCR fallback for scanned PDFs |
| `OCR_LANG` | `eng` | Tesseract language |
| `OCR_DPI` | `200` | OCR render DPI |
| `OCR_MIN_TEXT_CHARS` | `30` | OCR triggers if page text shorter than this |
| `TESSERACT_CMD` | _(empty)_ | Path to Tesseract binary (Windows) |
| `EXTRACTIVE_MIN_SCORE` | `0.12` | Min keyword overlap score (extractive mode) |
| `EXTRACTIVE_MAX_CHUNKS_SCAN` | `400` | Max chunks scanned (extractive mode) |

---

## Example Session

### Upload
```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@NexusCorp_Test_Document.pdf"
```
```json
{ "document_id": "751b2f23-...", "message": "Upload successful" }
```

### Chat
```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "751b2f23-...",
    "query": "Who must approve a MacBook Pro request?"
  }'
```
```json
{
  "answer": "A Vice President must approve a MacBook Pro request.",
  "source_pages": [4]
}
```

---

## Sample Verified Q&A (NexusCorp Handbook)

| Question | Answer | Page |
|---|---|---|
| How many days of PTO? | 22 days of Paid Time Off (PTO) per calendar year. | 2 |
| How many sick leave days? | Employees receive 10 days of paid sick leave. | 2 |
| Carry-over PTO rule? | Up to 5 days carry over; rest forfeited if not used by Dec 31. | 2 |
| Mandatory in-office days? | Mondays and Fridays. | 3 |
| Standard issued laptop? | Lenovo ThinkPad T14. | 4 |
| MacBook approval? | A Vice President. | 4 |
| Core mission? | Build sustainable, AI-driven solutions for the logistics industry. | 1 |
| Salary of a software engineer? | **Not found in document** | — |
| Does NexusCorp offer free lunch? | **Not found in document** | — |

---

## Switching LLM Providers

The provider layer in [app/services/model_providers.py](app/services/model_providers.py)
is pluggable. To add a new provider (e.g. Ollama, OpenAI, Gemini):

1. Implement a class with `async def answer(self, *, context: str, question: str) -> str`.
2. Register it in `get_providers()` under a new `LLM_PROVIDER` value.
3. Add the config keys to `Settings` in [app/core/config.py](app/core/config.py).
4. Set `LLM_PROVIDER=<your_provider>` in `.env`.

Built-in modes:

| `LLM_PROVIDER` | Behavior |
|---|---|
| `extractive` | No LLM; returns the highest-scoring sentence(s) verbatim from context. Fully offline. |
| `groq` | Calls Groq's free cloud LLM. Fluent answers + page citations. |

---

## Design Notes

- **Strict grounding.** The system prompt forbids outside knowledge. If the LLM can't find an answer in context, it must output exactly `"Not found in document"`.
- **Page-tagged context.** Before being sent to the LLM, each retrieved chunk is prefixed with `[page N]`. The model is instructed to cite these tokens in its answer; we parse them out to populate `source_pages` accurately.
- **Per-document isolation.** All chunks store a `document_id` payload; retrieval is filtered by it, so many PDFs can coexist safely in one Qdrant collection.
- **Hybrid extraction.** Selectable text first; if a page has < `OCR_MIN_TEXT_CHARS`, the page is rendered with PyMuPDF and run through Tesseract.
- **Hash embeddings.** Zero-dependency embedding via SHA-256 token hashing. Good enough for keyword-heavy retrieval; swap in real embeddings (sentence-transformers, OpenAI, Cohere) for semantic queries.
- **Graceful shutdown.** Qdrant client is closed in FastAPI's `shutdown` event to avoid `__del__` noise on interpreter teardown.

---

## Use Cases

- Internal Q&A bots over policy handbooks, SOPs, contracts, manuals
- Research assistants for academic papers / reports
- Customer-support knowledge bases built from product docs
- Compliance / legal review where every answer must cite a page
- Personal "chat with my PDFs" tool

---

## Security Notes

- **Never commit `.env`.** Add it to `.gitignore`. It contains your Groq API key.
- **Rotate keys** that leak via screenshots, chats, or shared logs.
- The Qdrant store is local and unauthenticated — do not expose this service publicly without adding auth (e.g. an API key on `/upload` and `/chat`).

---

## Requirements

- Python 3.11+ (tested on 3.12)
- Windows / macOS / Linux
- Tesseract OCR engine (only if you need OCR for scanned PDFs)
- Free Groq API key (or use `LLM_PROVIDER=extractive` to run fully offline)
