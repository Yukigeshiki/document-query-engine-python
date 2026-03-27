/**
 * Composable managing a list of ingested documents fetched from the backend.
 *
 * Each call creates its own state — no shared singletons.
 */

import { ref } from 'vue'
import { listDocuments } from '@/services/queryEngine'
import type { DocumentInfo } from '@/types/queryEngine'

export function useDocumentHistory() {
  const documents = ref<DocumentInfo[]>([])
  const total = ref(0)
  const isLoading = ref(false)
  const hasMore = ref(false)

  const PAGE_SIZE = 20

  /**
   * Fetch documents from the backend.
   * Returns the fetched documents so callers can use the fresh value directly.
   */
  async function fetchDocuments(): Promise<DocumentInfo[]> {
    isLoading.value = true
    try {
      const response = await listDocuments(PAGE_SIZE, 0)
      documents.value = response.documents
      total.value = response.total
      hasMore.value = response.documents.length < response.total
      return response.documents
    } catch (err) {
      console.error('Failed to fetch documents:', err)
      return []
    } finally {
      isLoading.value = false
    }
  }

  async function loadMore(): Promise<void> {
    if (isLoading.value || !hasMore.value) return
    isLoading.value = true
    try {
      const response = await listDocuments(PAGE_SIZE, documents.value.length)
      documents.value = [...documents.value, ...response.documents]
      total.value = response.total
      hasMore.value = documents.value.length < response.total
    } catch (err) {
      console.error('Failed to load more documents:', err)
    } finally {
      isLoading.value = false
    }
  }

  return {
    documents,
    total,
    isLoading,
    hasMore,
    fetchDocuments,
    loadMore,
  }
}
