import type { ChatResponse, DocumentListResponse, UploadResponse } from "@/lib/types";

async function readJsonSafe(resp: Response) {
  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function listDocuments(): Promise<DocumentListResponse> {
  const resp = await fetch("/api/documents", { cache: "no-store" });
  const data = (await readJsonSafe(resp)) as DocumentListResponse;
  if (!resp.ok) {
    throw new Error((data as any)?.detail || `Failed to load documents (${resp.status})`);
  }
  return data;
}

export async function uploadPdf(file: File): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch("/api/upload", { method: "POST", body: fd });
  const data = (await readJsonSafe(resp)) as UploadResponse;
  if (!resp.ok) {
    throw new Error((data as any)?.detail || `Upload failed (${resp.status})`);
  }
  return data;
}

export async function askDocument(documentId: string, query: string): Promise<ChatResponse> {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, query }),
  });
  const data = (await readJsonSafe(resp)) as ChatResponse;
  if (!resp.ok) {
    throw new Error((data as any)?.detail || `Chat failed (${resp.status})`);
  }
  return data;
}

