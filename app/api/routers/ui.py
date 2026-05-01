from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/ui", include_in_schema=False)
def ui() -> HTMLResponse:
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PDF RAG Chat – Test UI</title>
    <style>
      :root { color-scheme: light; }
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 0; background: #f7f7fb; color: #111827; }
      header { padding: 16px 20px; border-bottom: 1px solid #e5e7eb; background: #ffffff; }
      main { max-width: 980px; margin: 0 auto; padding: 20px; display: grid; gap: 16px; }
      .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
      @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
      .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; background: #ffffff; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
      h1 { font-size: 18px; margin: 0; }
      h2 { font-size: 14px; margin: 0 0 12px; opacity: .9; }
      label { display: block; font-size: 12px; margin: 10px 0 6px; opacity: .9; }
      input[type="text"], textarea { width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid #d1d5db; background: #ffffff; color: #111827; }
      textarea { min-height: 120px; resize: vertical; }
      button { padding: 10px 12px; border-radius: 10px; border: 1px solid #cbd5e1; background: #eef2ff; cursor: pointer; color: #1f2937; }
      button:disabled { opacity: .6; cursor: not-allowed; }
      .muted { font-size: 12px; opacity: .8; }
      code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
      pre { white-space: pre-wrap; word-break: break-word; margin: 10px 0 0; padding: 12px; border-radius: 10px; border: 1px solid #e5e7eb; background: #f9fafb; }
      .pill { display:inline-flex; gap:8px; align-items:center; padding:6px 10px; border-radius:999px; border: 1px solid #e5e7eb; }
      .ok { background: #ecfdf5; color: #065f46; }
      .err { background: #fef2f2; color: #991b1b; }
      .grid2 { display:grid; grid-template-columns: 1fr auto; gap: 10px; align-items: end; }
      .out { font-size: 14px; line-height: 1.45; }
    </style>
  </head>
  <body>
    <header>
      <h1>PDF RAG Chat – Test UI</h1>
      <div class="muted">Use this page to test <code>POST /upload</code> and <code>POST /chat</code> quickly.</div>
    </header>

    <main>
      <div class="row">
        <section class="card">
          <h2>1) Upload PDF</h2>
          <form id="uploadForm">
            <label for="pdfFile">PDF file</label>
            <input id="pdfFile" name="file" type="file" accept="application/pdf" required />
            <div style="height:10px"></div>
            <button id="uploadBtn" type="submit">Upload</button>
          </form>
          <div style="height:10px"></div>
          <div id="uploadStatus" class="pill ok" style="display:none"></div>
          <pre id="uploadOut" class="out" style="display:none"></pre>
        </section>

        <section class="card">
          <h2>2) Chat</h2>
          <div class="grid2">
            <div>
              <label for="documentId">document_id</label>
              <input id="documentId" type="text" placeholder="Paste document_id from upload response" />
            </div>
            <button id="useLastBtn" type="button" title="Use document_id from last upload">Use last</button>
          </div>
          <label for="query">Query</label>
          <textarea id="query" placeholder="Ask a question about the uploaded PDF..."></textarea>
          <div style="height:10px"></div>
          <button id="chatBtn" type="button">Ask</button>
          <div style="height:10px"></div>
          <div id="chatStatus" class="pill ok" style="display:none"></div>
          <pre id="chatOut" class="out" style="display:none"></pre>
        </section>
      </div>

      <section class="card">
        <h2>Debug log</h2>
        <div class="muted">Shows the last request/response errors.</div>
        <pre id="log"></pre>
      </section>
    </main>

    <script>
      const $ = (id) => document.getElementById(id);
      const logEl = $("log");
      let lastDocumentId = "";

      function log(line) {
        const now = new Date().toISOString();
        logEl.textContent = `[${now}] ${line}\\n` + logEl.textContent;
      }

      function setStatus(el, ok, text) {
        el.style.display = "inline-flex";
        el.classList.toggle("ok", ok);
        el.classList.toggle("err", !ok);
        el.textContent = text;
      }

      async function readJsonSafe(resp) {
        const text = await resp.text();
        try { return JSON.parse(text); } catch { return { raw: text }; }
      }

      $("uploadForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const file = $("pdfFile").files?.[0];
        if (!file) return;

        $("uploadBtn").disabled = true;
        $("uploadOut").style.display = "none";
        $("uploadStatus").style.display = "none";

        try {
          log(`Uploading: ${file.name} (${file.size} bytes)`);
          const fd = new FormData();
          fd.append("file", file);

          const resp = await fetch("/upload", { method: "POST", body: fd });
          const data = await readJsonSafe(resp);
          $("uploadOut").style.display = "block";
          if (resp.ok) {
            $("uploadOut").textContent =
              `Upload successful\\n` +
              `document_id: ${data.document_id || ""}\\n` +
              `message: ${data.message || ""}`.trim();
          } else {
            $("uploadOut").textContent =
              `Upload failed\\n` +
              `status: ${resp.status}\\n` +
              `detail: ${(data && data.detail) ? data.detail : JSON.stringify(data)}`.trim();
          }

          if (!resp.ok) {
            setStatus($("uploadStatus"), false, `Upload failed (${resp.status})`);
            log(`Upload error ${resp.status}: ${JSON.stringify(data)}`);
            return;
          }

          lastDocumentId = data.document_id || "";
          if (lastDocumentId) $("documentId").value = lastDocumentId;
          setStatus($("uploadStatus"), true, "Upload successful");
          log(`Upload ok. document_id=${lastDocumentId}`);
        } catch (err) {
          setStatus($("uploadStatus"), false, "Upload failed (network)");
          log(`Upload network error: ${err}`);
        } finally {
          $("uploadBtn").disabled = false;
        }
      });

      $("useLastBtn").addEventListener("click", () => {
        if (lastDocumentId) $("documentId").value = lastDocumentId;
      });

      $("chatBtn").addEventListener("click", async () => {
        const documentId = ($("documentId").value || "").trim();
        const query = ($("query").value || "").trim();
        if (!documentId) { alert("document_id is required"); return; }
        if (!query) { alert("query is required"); return; }

        $("chatBtn").disabled = true;
        $("chatOut").style.display = "none";
        $("chatStatus").style.display = "none";

        try {
          log(`Chat request doc=${documentId} q="${query.slice(0, 80)}"`);
          const resp = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ document_id: documentId, query }),
          });

          const data = await readJsonSafe(resp);
          $("chatOut").style.display = "block";
          if (resp.ok) {
            const pages = (data.source_pages || []).join(", ");
            $("chatOut").textContent =
              `Query:\\n${query}\\n\\n` +
              `Answer:\\n${data.answer || \"\"}\\n\\n` +
              `Source pages: ${pages || \"(none)\"}`.trim();
          } else {
            $("chatOut").textContent =
              `Chat failed\\n` +
              `status: ${resp.status}\\n` +
              `detail: ${(data && data.detail) ? data.detail : JSON.stringify(data)}`.trim();
          }

          if (!resp.ok) {
            setStatus($("chatStatus"), false, `Chat failed (${resp.status})`);
            log(`Chat error ${resp.status}: ${JSON.stringify(data)}`);
            return;
          }

          setStatus($("chatStatus"), true, "Chat successful");
          log(`Chat ok. pages=${(data.source_pages || []).join(",")}`);
        } catch (err) {
          setStatus($("chatStatus"), false, "Chat failed (network)");
          log(`Chat network error: ${err}`);
        } finally {
          $("chatBtn").disabled = false;
        }
      });
    </script>
  </body>
</html>
"""
    return HTMLResponse(content=html)
