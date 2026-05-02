"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { askDocument, listDocuments, uploadPdf } from "@/lib/api";
import type { ChatMessage, DocumentMeta, PersistedState } from "@/lib/types";
import { loadState, saveState } from "@/lib/storage";
import {
  BoltIcon,
  BotIcon,
  CheckIcon,
  CloseIcon,
  DownloadIcon,
  FileIcon,
  GearIcon,
  HelpIcon,
  HistoryIcon,
  PaperclipIcon,
  PlusIcon,
  RefreshIcon,
  SendIcon,
  UserIcon,
} from "@/components/icons";

function fmtBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function makeId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function deriveTags(filename: string, pageCount: number): string[] {
  const base = (filename || "").toLowerCase();
  const tags: string[] = [];
  if (/financ|q[1-4]|report|earning/.test(base)) tags.push("FINANCE");
  if (/q1|q2|q3|q4/.test(base)) {
    const m = base.match(/q[1-4]/);
    if (m) tags.push(`${m[0].toUpperCase()} 2026`);
  }
  if (/policy|handbook|hr|employee|confidential/.test(base)) tags.push("CONFIDENTIAL");
  if (/manual|spec|design/.test(base)) tags.push("INTERNAL");
  if (!tags.length) {
    tags.push("PDF");
    if (pageCount >= 20) tags.push("LONG");
  }
  return tags;
}

export default function HomePage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const [activeTopTab, setActiveTopTab] = useState<"documents" | "history">("documents");
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [messagesByDocument, setMessagesByDocument] = useState<Record<string, ChatMessage[]>>({});

  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const selectedDocument = useMemo(() => {
    if (!selectedDocumentId) return null;
    return documents.find((d) => d.document_id === selectedDocumentId) || null;
  }, [documents, selectedDocumentId]);

  const messages = useMemo(() => {
    if (!selectedDocumentId) return [];
    return messagesByDocument[selectedDocumentId] || [];
  }, [messagesByDocument, selectedDocumentId]);

  async function refreshDocuments(preferredSelectedId?: string | null) {
    setError(null);
    const data = await listDocuments();
    setDocuments(data.documents || []);
    const desired = preferredSelectedId ?? selectedDocumentId;
    const found = desired ? data.documents?.some((d) => d.document_id === desired) : false;
    if (desired && found) setSelectedDocumentId(desired);
    else if (data.documents?.length) setSelectedDocumentId(data.documents[0].document_id);
    else setSelectedDocumentId(null);
  }

  useEffect(() => {
    const persisted = loadState();
    const persistedSelectedId = persisted?.selectedDocumentId || null;
    if (persisted) {
      setSelectedDocumentId(persistedSelectedId);
      setMessagesByDocument(persisted.messagesByDocument || {});
    }
    refreshDocuments(persistedSelectedId).catch((e) => setError(String(e?.message || e)));
  }, []);

  useEffect(() => {
    const state: PersistedState = { selectedDocumentId, messagesByDocument };
    saveState(state);
  }, [messagesByDocument, selectedDocumentId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, asking]);

  function pickFile() {
    fileInputRef.current?.click();
  }

  async function handleUpload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const resp = await uploadPdf(file);
      await refreshDocuments(resp.document_id);
      setSelectedDocumentId(resp.document_id);
      setActiveTopTab("documents");
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setUploading(false);
    }
  }

  function onFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = "";
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  }

  function newChat() {
    if (!selectedDocumentId) return;
    setMessagesByDocument((prev) => ({ ...prev, [selectedDocumentId]: [] }));
  }

  function clearSelection() {
    setSelectedDocumentId(null);
  }

  function exportChat() {
    if (!selectedDocumentId) return;
    const doc = selectedDocument;
    const payload = {
      document_id: selectedDocumentId,
      filename: doc?.filename || null,
      exported_at: new Date().toISOString(),
      messages,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${selectedDocumentId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function openDocument() {
    if (!selectedDocumentId) return;
    window.open(`/api/documents/${selectedDocumentId}/file`, "_blank", "noopener,noreferrer");
  }

  async function sendQuery() {
    const docId = selectedDocumentId;
    const q = query.trim();
    if (!docId || !q) return;
    setQuery("");
    setError(null);

    const userMsg: ChatMessage = {
      id: makeId(),
      role: "user",
      content: q,
      createdAt: new Date().toISOString(),
    };
    setMessagesByDocument((prev) => ({ ...prev, [docId]: [...(prev[docId] || []), userMsg] }));

    setAsking(true);
    try {
      const resp = await askDocument(docId, q);
      const assistantMsg: ChatMessage = {
        id: makeId(),
        role: "assistant",
        content: resp.answer,
        source_pages: resp.source_pages || [],
        citations: resp.citations || [],
        createdAt: new Date().toISOString(),
      };
      setMessagesByDocument((prev) => ({ ...prev, [docId]: [...(prev[docId] || []), assistantMsg] }));
    } catch (e: any) {
      setError(e?.message || String(e));
      const assistantMsg: ChatMessage = {
        id: makeId(),
        role: "assistant",
        content: "Sorry — something went wrong while answering.",
        createdAt: new Date().toISOString(),
      };
      setMessagesByDocument((prev) => ({ ...prev, [docId]: [...(prev[docId] || []), assistantMsg] }));
    } finally {
      setAsking(false);
    }
  }

  const historyItems = useMemo(() => {
    const items: Array<{ document: DocumentMeta; last: ChatMessage | null; count: number }> = [];
    for (const doc of documents) {
      const msgs = messagesByDocument[doc.document_id] || [];
      items.push({
        document: doc,
        last: msgs.length ? msgs[msgs.length - 1] : null,
        count: msgs.length,
      });
    }
    items.sort((a, b) =>
      (b.last?.createdAt || b.document.created_at).localeCompare(a.last?.createdAt || a.document.created_at)
    );
    return items;
  }, [documents, messagesByDocument]);

  return (
    <div>
      <header className="topNav">
        <div className="navLeft">
          <div className="brand">
            <span className="brandIcon">
              <FileIcon size={24} />
            </span>
            Nexus PDF
          </div>
          <nav className="navLinks" aria-label="Top navigation">
            <button
              type="button"
              className={`navLink ${activeTopTab === "documents" ? "navLinkActive" : ""}`}
              onClick={() => setActiveTopTab("documents")}
            >
              Documents
            </button>
            <button
              type="button"
              className={`navLink ${activeTopTab === "history" ? "navLinkActive" : ""}`}
              onClick={() => setActiveTopTab("history")}
            >
              History
            </button>
          </nav>
        </div>

        <div className="actions">
          <button
            className="primaryBtn"
            type="button"
            onClick={newChat}
            disabled={!selectedDocumentId}
            title="Start a new chat for the selected document"
          >
            <PlusIcon />
            New Chat
          </button>
          <button className="iconBtn" type="button" title="Settings" aria-label="Settings">
            <GearIcon />
          </button>
          <button className="iconBtn" type="button" title="Help" aria-label="Help">
            <HelpIcon />
          </button>
          <button className="profileBtn" type="button" title="Profile" aria-label="Profile">
            <UserIcon size={18} />
          </button>
        </div>
      </header>

      {activeTopTab === "history" ? (
        <main className="mainGrid">
          <section className="col">
            <div className="card docCard">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>Recent Chats</div>
                <button
                  className="linkBtn"
                  type="button"
                  onClick={() => refreshDocuments()}
                  disabled={uploading || asking}
                >
                  <RefreshIcon size={16} />
                  Refresh
                </button>
              </div>
              <div style={{ height: 12 }} />
              <div className="docList">
                {historyItems.map((it) => (
                  <button
                    key={it.document.document_id}
                    type="button"
                    className={`docListItem ${
                      selectedDocumentId === it.document.document_id ? "docListItemActive" : ""
                    }`}
                    onClick={() => {
                      setSelectedDocumentId(it.document.document_id);
                      setActiveTopTab("documents");
                    }}
                  >
                    <span className="docHeadIcon" style={{ width: 36, height: 36 }}>
                      <FileIcon size={18} />
                    </span>
                    <div style={{ textAlign: "left" }}>
                      <div className="docListItemTitle">{it.document.filename}</div>
                      <div className="docListItemSub">
                        {it.count ? `${it.count} messages` : "No messages yet"}
                      </div>
                    </div>
                    <div className="docListItemRight">{it.document.page_count} pages</div>
                  </button>
                ))}
                {!historyItems.length ? (
                  <div style={{ color: "var(--muted)", fontSize: 13 }}>No documents yet.</div>
                ) : null}
              </div>
            </div>
          </section>
          <section className="col">
            <div className="card chatShell">
              <div className="chatHeader">
                <div>
                  <h1 className="chatTitle">History</h1>
                  <div className="chatSub">Pick a document to jump back into a chat.</div>
                </div>
              </div>
              <div className="chatBody" style={{ color: "var(--muted)" }}>
                Select a conversation from the left.
              </div>
            </div>
          </section>
        </main>
      ) : (
        <main className="mainGrid">
          <section className="col">
            <div
              className="card uploadCard"
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              role="region"
              aria-label="Upload new document"
            >
              <div className="uploadInner">
                <span className="uploadIconWrap">
                  <FileIcon size={26} />
                </span>
                <div className="uploadTitle">Upload new document</div>
                <div className="uploadHint">Drag &amp; drop PDF here, or click to browse</div>
                <button className="selectBtn" type="button" onClick={pickFile} disabled={uploading}>
                  {uploading ? "Uploading..." : "Select File"}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  onChange={onFilePicked}
                  style={{ display: "none" }}
                />
              </div>
            </div>

            {selectedDocument ? (
              <div className="card docCard">
                <div className="docHead">
                  <div className="docHeadIcon">
                    <FileIcon size={18} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="docName" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {selectedDocument.filename}
                    </div>
                    <div className="docMeta">
                      {fmtBytes(selectedDocument.size_bytes)} • {selectedDocument.page_count} Pages
                    </div>
                  </div>
                  <button
                    className="docClose"
                    type="button"
                    onClick={clearSelection}
                    title="Deselect document"
                    aria-label="Deselect document"
                  >
                    <CloseIcon size={16} />
                  </button>
                </div>

                <div className="docStatus">
                  <span className="statusCheck">
                    <CheckIcon size={12} />
                  </span>
                  Document processed and ready for querying.
                </div>

                <div className="tagRow">
                  {deriveTags(selectedDocument.filename, selectedDocument.page_count).map((t) => (
                    <span className="tag" key={t}>
                      {t}
                    </span>
                  ))}
                </div>

                <div className="preview" aria-hidden="true">
                  <div className="previewMask" />
                </div>

                <button className="viewBtn" type="button" onClick={openDocument}>
                  <FileIcon size={18} />
                  View Document
                </button>
              </div>
            ) : null}

            <div className="card docCard">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                <div style={{ fontWeight: 800, fontSize: 16 }}>Documents</div>
                <button
                  className="linkBtn"
                  type="button"
                  onClick={() => refreshDocuments()}
                  disabled={uploading || asking}
                >
                  <RefreshIcon size={16} />
                  Refresh
                </button>
              </div>
              <div style={{ height: 12 }} />
              <div className="docList">
                {documents.map((d) => (
                  <button
                    key={d.document_id}
                    type="button"
                    className={`docListItem ${
                      selectedDocumentId === d.document_id ? "docListItemActive" : ""
                    }`}
                    onClick={() => setSelectedDocumentId(d.document_id)}
                  >
                    <span className="docHeadIcon" style={{ width: 36, height: 36 }}>
                      <FileIcon size={18} />
                    </span>
                    <div style={{ textAlign: "left", minWidth: 0, flex: 1 }}>
                      <div
                        className="docListItemTitle"
                        style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                      >
                        {d.filename}
                      </div>
                      <div className="docListItemSub">
                        {fmtBytes(d.size_bytes)} • {d.page_count} pages
                      </div>
                    </div>
                    <div className="docListItemRight">{d.status}</div>
                  </button>
                ))}
                {!documents.length ? (
                  <div style={{ color: "var(--muted)", fontSize: 13 }}>
                    No documents yet. Upload a PDF to start.
                  </div>
                ) : null}
              </div>
            </div>
          </section>

          <section className="col">
            <div className="card chatShell">
              <div className="chatHeader">
                <div>
                  <h1 className="chatTitle">Chat Workspace</h1>
                  <div className="chatSub">
                    {selectedDocument ? (
                      <>
                        Ask questions about <strong>{selectedDocument.filename}</strong>
                      </>
                    ) : (
                      "Upload a PDF and select it to start chatting."
                    )}
                  </div>
                </div>
                <div className="chatHeaderActions">
                  <button
                    className="linkBtn"
                    type="button"
                    disabled={!selectedDocumentId}
                    onClick={() => setActiveTopTab("history")}
                  >
                    <HistoryIcon size={16} />
                    History
                  </button>
                  <button
                    className="linkBtn"
                    type="button"
                    disabled={!selectedDocumentId || !messages.length}
                    onClick={exportChat}
                  >
                    <DownloadIcon size={16} />
                    Export
                  </button>
                </div>
              </div>

              <div className="chatBody" role="log" aria-label="Chat messages">
                {!messages.length && !asking ? (
                  <div className="msgRow">
                    <div className="avatar avatarBot" aria-hidden="true">
                      <BotIcon size={18} />
                    </div>
                    <div className="msgCol">
                      <div className="msgLabel">NEXUS AI</div>
                      <div className="msgBubble">
                        {selectedDocument
                          ? `I've analyzed the document. It contains ${selectedDocument.page_count} pages. What would you like to know?`
                          : "Upload and select a PDF to get started."}
                      </div>
                    </div>
                  </div>
                ) : null}

                {messages.map((m) => (
                  <div key={m.id} className={`msgRow ${m.role === "user" ? "msgUser" : ""}`}>
                    <div
                      className={`avatar ${m.role === "user" ? "avatarUser" : "avatarBot"}`}
                      aria-hidden="true"
                    >
                      {m.role === "user" ? <UserIcon size={18} /> : <BotIcon size={18} />}
                    </div>
                    <div className="msgCol">
                      <div className="msgLabel">{m.role === "user" ? "YOU" : "NEXUS AI"}</div>
                      <div className="msgBubble">
                        <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
                      </div>
                      {m.role === "assistant" && m.citations?.length ? (
                        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                          {m.citations.map((c, i) => (
                            <div className="citationBox" key={`${m.id}-c-${i}`}>
                              <div className="citationHead">
                                <FileIcon size={14} />
                                Page {c.page}
                              </div>
                              <div className="citationQuote">&quot;{c.quote}&quot;</div>
                            </div>
                          ))}
                        </div>
                      ) : m.role === "assistant" && m.source_pages?.length ? (
                        <div className="citationBox" style={{ marginTop: 10 }}>
                          <div className="citationHead">
                            <FileIcon size={14} />
                            Source pages
                          </div>
                          <div style={{ fontSize: 13 }}>{m.source_pages.join(", ")}</div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}

                {asking ? (
                  <div className="msgRow">
                    <div className="avatar avatarBot" aria-hidden="true">
                      <BotIcon size={18} />
                    </div>
                    <div className="msgCol">
                      <div className="msgLabel">NEXUS AI</div>
                      <div className="msgBubble">Thinking…</div>
                    </div>
                  </div>
                ) : null}
                <div ref={chatEndRef} />
              </div>

              <div className="chatComposer">
                <div className="composerWrap">
                  <span className="composerIcon" aria-hidden="true">
                    <PaperclipIcon size={18} />
                  </span>
                  <textarea
                    className="composerInput"
                    placeholder="Ask a question about the document..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        sendQuery();
                      }
                    }}
                    disabled={!selectedDocumentId || uploading || asking}
                    rows={1}
                  />
                </div>
                <button
                  className="sendBtn"
                  type="button"
                  onClick={sendQuery}
                  disabled={!selectedDocumentId || !query.trim() || uploading || asking}
                  aria-label="Send"
                >
                  <SendIcon size={18} />
                </button>
              </div>

              <div className="footerNote">
                <span className="bolt">
                  <BoltIcon size={14} />
                </span>
                Nexus AI can make mistakes. Verify important info.
              </div>
            </div>

            {error ? (
              <div className="card docCard errorCard">
                <div className="errorTitle">Error</div>
                <div className="errorBody">{error}</div>
              </div>
            ) : null}
          </section>
        </main>
      )}
    </div>
  );
}
