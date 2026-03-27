/** TypeScript interfaces matching the query engine backend response models. */

export interface SubgraphNode {
  id: string
  label: string | null
  properties: Record<string, string>
}

export interface SubgraphEdge {
  source: string
  target: string
  relation: string
}

export interface SubgraphResponse {
  entity: string
  depth: number
  nodes: SubgraphNode[]
  edges: SubgraphEdge[]
}

export type TaskStatus = 'pending' | 'started' | 'success' | 'failure' | 'revoked'

export interface TaskStatusResponse {
  taskId: string
  status: TaskStatus
  result: IngestResult | null
  error: string | null
}

export interface UploadAcceptedResponse {
  taskId: string
}

export interface IngestResult {
  sourceType: string
  totalDocuments: number
  totalTriplets: number
  errors: string[]
}

export interface DocumentInfo {
  docId: string
  docIds: string[]
  fileName: string | null
  nodeCount: number
  metadata: Record<string, unknown>
}

export interface DocumentListResponse {
  documents: DocumentInfo[]
  total: number
  limit: number
  offset: number
}
