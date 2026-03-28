/** API functions for the query engine backend. */

import { apiClient } from './api'
import type {
  DocumentListResponse,
  QueryResponse,
  RetrievalMode,
  SubgraphResponse,
  TaskStatusResponse,
  UploadAcceptedResponse,
} from '@/types/queryEngine'

/**
 * Upload a document for async ingestion into the knowledge graph.
 *
 * @param file - The file to upload (PDF, DOCX, or TXT).
 * @returns The accepted response with a task ID for polling.
 */
export async function uploadDocument(file: File): Promise<UploadAcceptedResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await apiClient.post<UploadAcceptedResponse>(
    '/api/v1/kg/ingest/upload',
    formData,
  )
  return data
}

/**
 * Poll the status of a background task.
 *
 * @param taskId - The task ID returned from an upload or ingest request.
 * @returns The current task status, result, or error.
 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  const { data } = await apiClient.get<TaskStatusResponse>(
    `/api/v1/tasks/${taskId}`,
  )
  return data
}

/**
 * Fetch a subgraph centered on a specific entity.
 *
 * @param entity - The entity name to center the subgraph on.
 * @param depth - Traversal depth (1-5, default 2).
 * @returns The subgraph with nodes and edges.
 */
export async function getSubgraph(
  entity: string,
  depth: number = 2,
): Promise<SubgraphResponse> {
  const { data } = await apiClient.get<SubgraphResponse>(
    '/api/v1/kg/subgraph',
    { params: { entity, depth } },
  )
  return data
}


/**
 * List ingested documents with pagination (newest first).
 *
 * @param limit - Max documents to return (1-100, default 20).
 * @param offset - Number of documents to skip (default 0).
 * @returns Paginated document list with total count.
 */
export async function listDocuments(
  limit: number = 20,
  offset: number = 0,
): Promise<DocumentListResponse> {
  const { data } = await apiClient.get<DocumentListResponse>(
    '/api/v1/kg/documents',
    { params: { limit, offset } },
  )
  return data
}

/**
 * Fetch the graph for a specific ingested document.
 *
 * @param docIds - The document IDs to fetch the graph for (supports multi-chunk docs).
 * @returns The subgraph containing only that document's entities and relationships.
 */
export async function getDocumentGraph(docIds: string[]): Promise<SubgraphResponse> {
  const { data } = await apiClient.get<SubgraphResponse>(
    '/api/v1/kg/documents/graph',
    { params: { doc_ids: docIds } },
  )
  return data
}

/**
 * Query the knowledge graph with a natural language question.
 *
 * @param query - The question to ask.
 * @param retrievalMode - Retrieval strategy: dual, kg_only, or vector_only.
 * @returns The response text and source nodes.
 */
export async function queryKnowledgeGraph(
  query: string,
  retrievalMode: RetrievalMode = 'dual',
): Promise<QueryResponse> {
  const { data } = await apiClient.post<QueryResponse>(
    '/api/v1/kg/query',
    { query, retrievalMode },
  )
  return data
}
