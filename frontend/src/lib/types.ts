export type DocumentMeta = {
  document_id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  created_at: string;
  tags: string[];
  status: string;
};

export type DocumentListResponse = {
  documents: DocumentMeta[];
  total: number;
};

export type UploadResponse = {
  document_id: string;
  message: string;
  filename?: string | null;
  size_bytes?: number | null;
  page_count?: number | null;
};

export type Citation = {
  page: number;
  quote: string;
};

export type ChatResponse = {
  answer: string;
  source_pages: number[];
  citations?: Citation[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  source_pages?: number[];
  citations?: Citation[];
  createdAt: string;
};

export type PersistedState = {
  selectedDocumentId: string | null;
  messagesByDocument: Record<string, ChatMessage[]>;
};

