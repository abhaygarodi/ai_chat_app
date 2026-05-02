# Nexus PDF — RAG Chat App

A FastAPI + Next.js app that lets you **upload a PDF and ask questions about its content**. Answers are grounded in the document, cite the source page(s), and include a short verbatim quote per cited page. If the answer isn't in the document, it returns `"Not found in document"`.

The frontend is a polished "Nexus PDF" UI (drag-and-drop upload, document panel with status & tags, chat workspace with per-page citations and quotes).

---

## Features

- **PDF upload** with automatic text extraction
- **OCR fallback** for scanned / image-only PDFs (Tesseract)
- **Chunking** with LangChain's recursive splitter
- **Vector storage** via Qdrant (local file-backed or Qdrant Cloud)
- **Retrieval-Augmented Generation (RAG)** with top-K cosine search filtered by `document_id`
- **LLM answers** via Groq (free tier, `llama-3.1-8b-instant`)
- **Graceful offline fallback** — if the configured LLM is unavailable (bad API key, network issue), the system automatically falls back to the offline extractive provider so chat still works
- **Per-page citations with quotes** — each answer reports which page(s) it came from and includes a short verbatim excerpt per page
- **Strict grounding** — answers come only from the uploaded PDF
- **Browser test UI** at `/ui` (lightweight) and a full Next.js UI at `localhost:3000`
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
                │  Groq LLM ── on error ──▶ Extractive fallback
                │     │       │
                │     ▼       │
                │  Parse [page N] tokens / match answer to chunks
                │     │       │
                │     ▼       │
                │  Build per-page citations with quotes
                └─────────────┘
                       │
                       ▼
   { "answer": "...", "source_pages": [2], "citations": [{page, quote}] }
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
| Vector store | Qdrant (local persistent or cloud) | [app/core/database.py](app/core/database.py) |
| Retrieval | Qdrant `query_points` + payload filter | [app/services/rag_service.py](app/services/rag_service.py) |
| LLM | Groq (`llama-3.1-8b-instant`) | [app/services/model_providers.py](app/services/model_providers.py) |
| Document store | JSON-backed local store | [app/services/document_store.py](app/services/document_store.py) |
| Config | Pydantic Settings + `.env` | [app/core/config.py](app/core/config.py) |
| Built-in test UI | Static HTML page | [app/api/routers/ui.py](app/api/routers/ui.py) |
| Polished UI | Next.js 14 (App Router) | [frontend/](frontend/) |

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
│   │       ├── documents.py          # GET /documents, /documents/{id}, /documents/{id}/file
│   │       └── ui.py                 # GET  /ui (lightweight test page)
│   ├── core/
│   │   ├── config.py                 # Pydantic settings (env-driven)
│   │   ├── database.py               # Qdrant client singleton
│   │   └── exceptions.py             # UpstreamUnavailableError
│   ├── schemas/
│   │   ├── upload.py                 # UploadResponse model
│   │   ├── chat.py                   # ChatRequest / ChatResponse / Citation models
│   │   └── documents.py              # DocumentMeta / DocumentListResponse
│   └── services/
│       ├── pdf_service.py            # PDF → chunks (with OCR fallback)
│       ├── rag_service.py            # ingest + retrieve + answer + citations + LLM fallback
│       ├── document_store.py         # JSON-backed metadata store
│       └── model_providers.py        # Embeddings + LLM provider classes
├── frontend/                         # Next.js "Nexus PDF" UI
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx              # Documents / Chat workspace / History
│   │   │   └── globals.css
│   │   ├── components/icons.tsx      # SVG icon set
│   │   └── lib/{api,types,storage}.ts
│   ├── package.json
│   └── next.config.mjs               # /api/* → backend proxy
├── data/                             # uploads + documents.json (auto-created)
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
  "message": "Upload successful",
  "filename": "NexusCorp_Handbook.pdf",
  "size_bytes": 248213,
  "page_count": 12
}
```

**Errors:**
- `400` — empty file or no extractable text
- `415` — non-PDF content type
- `503` — embedding provider unavailable

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
  "answer": "Full-time employees receive 22 days of Paid Time Off (PTO) per calendar year.",
  "source_pages": [2],
  "citations": [
    {
      "page": 2,
      "quote": "Time Off Full-time employees receive 22 days of Paid Time Off (PTO) per calendar year. Employees receive 10 days of paid sick leave annually."
    }
  ]
}
```

**Out-of-document behavior:**
```json
{
  "answer": "Not found in document",
  "source_pages": [],
  "citations": []
}
```

---

### `GET /documents`
List uploaded documents and their metadata.

**Response** `200 OK`:
```json
{
  "documents": [
    {
      "document_id": "...",
      "filename": "NexusCorp_Handbook.pdf",
      "size_bytes": 248213,
      "page_count": 12,
      "created_at": "2026-05-02T12:00:00Z",
      "tags": [],
      "status": "ready"
    }
  ],
  "total": 1
}
```

### `GET /documents/{document_id}`
Fetch a single document's metadata. Returns `404` if not found.

### `GET /documents/{document_id}/file`
Download / view the originally uploaded PDF (sets `Content-Type: application/pdf`). Returns `404` if not found.

### `GET /healthz`
Liveness probe → `{"status":"ok"}`

### `GET /ui`
Built-in lightweight browser test page (single-file HTML + JS). Useful for quick smoke testing without running the Next.js frontend.

### `GET /docs`
Auto-generated Swagger UI.

---

## Setup

### 1. Install backend dependencies
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

### 3. (Optional) Get a free Groq API key

If you want **fluent LLM-generated answers**, you need a Groq API key. Without one, the app still works in offline extractive mode (it returns the most relevant sentences verbatim from the PDF).

**Steps to enable the LLM:**

1. Go to **https://console.groq.com/keys** and sign in (free).
2. Click **"Create API Key"** → copy the generated key (it starts with `gsk_...`).
3. Open the `.env` file in the project root and **paste your key** in place of the existing value:
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_paste_your_key_here
   GROQ_MODEL=llama-3.1-8b-instant
   ```
4. **Save** the file and **restart the backend** (`Ctrl+C`, then `python -m uvicorn app.main:app --reload --port 8000`) so it picks up the new key.

> **No Groq key, or key not working?** No problem. Set `LLM_PROVIDER=extractive` in `.env` to run fully offline. Or leave `LLM_PROVIDER=groq` with an invalid/missing key — the app **automatically falls back to the offline extractive provider** on chat requests, so the system never breaks.

> **Tip:** if you already have an API key from another LLM provider (OpenAI, Anthropic, Together, etc.), see [Switching LLM Providers](#switching-llm-providers) below — you can plug in any provider that exposes an `async answer(context, question)` method. The default is Groq because they have a free tier.

### 4. Run the backend
```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Open:
- **Lightweight test UI** → http://127.0.0.1:8000/ui
- **Swagger** → http://127.0.0.1:8000/docs

### 5. Run the Next.js frontend (Nexus PDF UI)

The polished UI lives in `frontend/`. It supports:
- Drag-and-drop PDF upload + click-to-browse
- Document panel (size/pages, ready status, auto-derived tags, preview, "View Document")
- Chat workspace with per-message **page citations and verbatim quotes**
- History tab listing all documents and chats
- New Chat / Export (downloads chat JSON)
- Local persistence of selected document and chat history (browser storage)

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

The frontend proxies `/api/*` to the backend using a Next.js rewrite. By default it targets `http://127.0.0.1:8000`. To point at a different backend:
```powershell
$env:BACKEND_URL="http://127.0.0.1:8000"
npm run dev
```

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `extractive` | `groq` (cloud LLM) or `extractive` (no-LLM offline). When set to `groq`, an automatic fallback to extractive kicks in on Groq errors. |
| `EMBEDDINGS_PROVIDER` | `hash` | Hash-based embeddings (no model download) |
| `HASH_EMBEDDING_DIM` | `1024` | Embedding vector dimension |
| `GROQ_API_KEY` | _(empty)_ | Your Groq API key (only required for `LLM_PROVIDER=groq`) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq chat model |
| `GROQ_TIMEOUT` | `30` | HTTP timeout (seconds) |
| `GROQ_TEMPERATURE` | `0.0` | Sampling temperature |
| `QDRANT_URL` | _(empty)_ | If set, use Qdrant Cloud at this URL |
| `QDRANT_API_KEY` | _(empty)_ | Qdrant Cloud API key |
| `QDRANT_PATH` | `./qdrant_data` | Local Qdrant data dir (used when `QDRANT_URL` is empty) |
| `QDRANT_COLLECTION` | `pdf_chunks` | Collection name |
| `QDRANT_RECREATE_ON_DIM_MISMATCH` | `true` | Wipe collection on dim change |
| `DATA_DIR` | `./data` | Local data dir |
| `UPLOAD_DIR` | `./data/uploads` | Stored PDFs |
| `DOCUMENTS_DB_PATH` | `./data/documents.json` | JSON-backed metadata store |
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
| `CORS_ALLOW_ORIGINS` | `["*"]` | CORS allow-list |

---

## Example Session

### Upload
```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@NexusCorp_Test_Document.pdf"
```
```json
{ "document_id": "751b2f23-...", "message": "Upload successful", "filename": "...", "size_bytes": 14546, "page_count": 4 }
```

### List documents
```bash
curl http://127.0.0.1:8000/documents
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
  "source_pages": [4],
  "citations": [
    { "page": 4, "quote": "Equipment requests for MacBook Pro must be approved by a Vice President." }
  ]
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
| `groq` | Calls Groq's free cloud LLM. Fluent answers + page citations. **Auto-falls-back to extractive on any Groq failure** so chat keeps working. |

---

## Design Notes

- **Strict grounding.** The system prompt forbids outside knowledge. If the LLM can't find an answer in context, it must output exactly `"Not found in document"`.
- **Page-tagged context.** Before being sent to the LLM, each retrieved chunk is prefixed with `[page N]`. The model is instructed to cite these tokens; we parse them out to populate `source_pages`.
- **Per-page quote citations.** For each cited page, the API returns a short verbatim excerpt from the chunk that supplied the answer, so the UI can render a "Page N" + quote block.
- **Resilient LLM.** When Groq is configured but the call fails (bad key, timeout, rate limit, network), the service silently falls back to the offline extractive provider over the same retrieved context. The system never returns a 5xx for this; it just degrades gracefully.
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
- Node 18+ (for the Next.js frontend)
- Windows / macOS / Linux
- Tesseract OCR engine (only if you need OCR for scanned PDFs)
- Free Groq API key (optional — `LLM_PROVIDER=extractive` runs fully offline)
