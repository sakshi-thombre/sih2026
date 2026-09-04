import { apiRequest } from './api';

export type UploadedDocument = Record<string, unknown>;

export interface SearchResult {
  document_id: string;
  filename: string;
  chunk_id: string;
  text: string;
  score: number;
  page_number: number | null;
  chunk_index: number;
}

export async function uploadDocument(file: File): Promise<UploadedDocument> {
  const formData = new FormData();
  formData.append('file', file);
  const data = await apiRequest<{ document: UploadedDocument }>('/api/v1/documents/upload', {
    method: 'POST',
    formData,
  });
  return data.document;
}

export async function searchDocuments(query: string, topK = 5): Promise<SearchResult[]> {
  const data = await apiRequest<{ query: string; results: SearchResult[] }>(
    '/api/v1/documents/search',
    { method: 'POST', body: { query, top_k: topK } }
  );
  return data.results;
}
