<template>
  <AppLayout>
    <div class="max-w-6xl mx-auto space-y-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold">Upload Document</h1>
          <p class="text-muted-foreground mt-1">
            Upload a PDF, DOCX, or TXT file to ingest into the knowledge graph.
          </p>
        </div>

        <Button v-if="status === 'success'" variant="outline" @click="reset">
          Upload Another
        </Button>
        <Button v-if="status === 'failure'" variant="outline" @click="reset">
          Try Again
        </Button>
      </div>

      <!-- File drop zone (shown when idle) -->
      <FileDropZone
        v-if="status === 'idle'"
        @file-selected="onFileSelected"
      />

      <!-- Upload button (shown after file selected) -->
      <div v-if="status === 'idle' && file" class="flex gap-3">
        <button
          @click="startUpload"
          class="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Upload & Ingest
        </button>
      </div>

      <!-- Progress (shown during upload/processing) -->
      <IngestionProgress
        v-if="status !== 'idle'"
        :status="status"
        :task-id="taskId"
        :result="result"
        :error="error"
      />

      <!-- Delete error -->
      <p v-if="deleteError" class="text-sm text-destructive">
        {{ deleteError }}
      </p>

      <!-- Document history -->
      <DocumentList
        :documents="documents"
        :selected-id="selectedDocId"
        :deleting-id="deletingDocId"
        :has-more="hasMore"
        :is-loading="isLoadingDocs"
        @select-document="onSelectDocument"
        @delete-document="onRequestDelete"
        @load-more="loadMore"
      >
        <template #above-selected>
          <div v-if="showGraph" class="space-y-4 my-3">
            <div class="flex items-center gap-3">
              <h2 class="text-lg font-semibold">Knowledge Graph</h2>
              <span v-if="isLoadingGraph" class="text-xs text-muted-foreground">Loading graph...</span>
            </div>

            <!-- Entity search -->
            <div class="flex gap-2">
              <input
                v-model="searchEntity"
                placeholder="Search entity (e.g., Alice)..."
                class="flex-1 px-3 py-2 border border-input rounded-md text-sm bg-background"
                @keyup.enter="searchSubgraph"
              />
              <button
                @click="searchSubgraph"
                :disabled="!searchEntity.trim()"
                class="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                Focus
              </button>
              <button
                @click="loadDocumentGraph"
                class="px-4 py-2 border border-border rounded-md text-sm font-medium hover:bg-accent transition-colors"
              >
                Reset
              </button>
            </div>

            <!-- Graph error -->
            <p v-if="graphError" class="text-sm text-destructive">
              {{ graphError }}
            </p>

            <!-- Graph visualization -->
            <KnowledgeGraph
              v-if="graphNodes.length > 0"
              :nodes="graphNodes"
              :edges="graphEdges"
            />

            <p v-else-if="!isLoadingGraph && !graphError" class="text-sm text-muted-foreground">
              No graph data available. The knowledge graph may be empty.
            </p>
          </div>
        </template>
      </DocumentList>

      <!-- Delete confirmation dialog -->
      <DeleteDocumentDialog
        :doc="docToDelete"
        @update:doc="docToDelete = $event"
        @confirm="onConfirmDelete"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import AppLayout from '@/layouts/AppLayout.vue'
import FileDropZone from '@/components/upload/FileDropZone.vue'
import IngestionProgress from '@/components/upload/IngestionProgress.vue'
import KnowledgeGraph from '@/components/graph/KnowledgeGraph.vue'
import DocumentList from '@/components/upload/DocumentList.vue'
import DeleteDocumentDialog from '@/components/upload/DeleteDocumentDialog.vue'
import { Button } from '@/components/ui/button'
import { useFileUpload } from '@/composables/useFileUpload'
import { useDocumentHistory } from '@/composables/useDocumentHistory'
import { getSubgraph, getDocumentGraph, deleteDocument } from '@/services/queryEngine'
import { pollTask } from '@/composables/useTaskPoller'
import type { SubgraphNode, SubgraphEdge, DocumentInfo } from '@/types/queryEngine'

const { file, taskId, status, result, error, upload, reset: resetUpload } = useFileUpload()
const { documents, isLoading: isLoadingDocs, hasMore, fetchDocuments, loadMore } = useDocumentHistory()

const graphNodes = ref<SubgraphNode[]>([])
const graphEdges = ref<SubgraphEdge[]>([])
const isLoadingGraph = ref(false)
const graphError = ref<string | null>(null)
const searchEntity = ref('')
const selectedDocId = ref<string | null>(null)
const selectedDocIds = ref<string[]>([])

const showGraph = computed(() => status.value === 'success' || selectedDocId.value !== null)

onMounted(fetchDocuments)

function onFileSelected(selectedFile: File) {
  file.value = selectedFile
}

function startUpload() {
  selectedDocId.value = null
  upload()
}

async function loadDocumentGraph() {
  if (selectedDocIds.value.length === 0) return
  isLoadingGraph.value = true
  graphError.value = null
  try {
    const response = await getDocumentGraph(selectedDocIds.value)
    graphNodes.value = response.nodes
    graphEdges.value = response.edges
  } catch (err) {
    graphError.value = err instanceof Error ? err.message : 'Failed to load document graph'
  } finally {
    isLoadingGraph.value = false
  }
}

async function searchSubgraph() {
  if (!searchEntity.value.trim()) return
  isLoadingGraph.value = true
  graphError.value = null
  try {
    const response = await getSubgraph(searchEntity.value.trim())
    graphNodes.value = response.nodes
    graphEdges.value = response.edges
  } catch (err) {
    graphError.value = err instanceof Error ? err.message : 'Failed to load subgraph'
  } finally {
    isLoadingGraph.value = false
  }
}

async function onSelectDocument(doc: DocumentInfo) {
  // Toggle: clicking the same document again closes the graph
  if (selectedDocId.value === doc.docId) {
    selectedDocId.value = null
    selectedDocIds.value = []
    graphNodes.value = []
    graphEdges.value = []
    graphError.value = null
    return
  }

  selectedDocId.value = doc.docId
  selectedDocIds.value = doc.docIds
  isLoadingGraph.value = true
  graphError.value = null
  try {
    const response = await getDocumentGraph(doc.docIds)
    graphNodes.value = response.nodes
    graphEdges.value = response.edges
  } catch (err) {
    graphError.value = err instanceof Error ? err.message : 'Failed to load document graph'
  } finally {
    isLoadingGraph.value = false
  }
}

const deletingDocId = ref<string | null>(null)
const deleteError = ref<string | null>(null)
const docToDelete = ref<DocumentInfo | null>(null)
let cancelDeletePoller: (() => void) | null = null
onUnmounted(() => cancelDeletePoller?.())

function onRequestDelete(doc: DocumentInfo) {
  docToDelete.value = doc
}

async function onConfirmDelete(doc: DocumentInfo) {
  docToDelete.value = null
  deletingDocId.value = doc.docId
  deleteError.value = null
  try {
    const { taskId: deleteTaskId } = await deleteDocument(doc.docId)

    const poller = pollTask(deleteTaskId)
    cancelDeletePoller = poller.cancel
    await poller.promise

    if (selectedDocId.value === doc.docId) {
      selectedDocId.value = null
      selectedDocIds.value = []
      graphNodes.value = []
      graphEdges.value = []
      graphError.value = null
    }

    await fetchDocuments()
  } catch (err) {
    deleteError.value = err instanceof Error ? err.message : 'Failed to delete document'
  } finally {
    deletingDocId.value = null
    cancelDeletePoller = null
  }
}

function reset() {
  if (successResetTimer) {
    clearTimeout(successResetTimer)
    successResetTimer = null
  }
  resetUpload()
  graphNodes.value = []
  graphEdges.value = []
  graphError.value = null
  searchEntity.value = ''
  selectedDocId.value = null
  selectedDocIds.value = []
}

// When ingestion succeeds, refresh document list, load the new document's
// graph, and auto-reset to the upload form after 10 seconds.
let successResetTimer: ReturnType<typeof setTimeout> | null = null
onUnmounted(() => { if (successResetTimer) clearTimeout(successResetTimer) })

watch(status, async (newStatus) => {
  if (successResetTimer) {
    clearTimeout(successResetTimer)
    successResetTimer = null
  }
  if (newStatus === 'success') {
    successResetTimer = setTimeout(() => {
      resetUpload()
      selectedDocId.value = null
      selectedDocIds.value = []
      graphNodes.value = []
      graphEdges.value = []
      graphError.value = null
      searchEntity.value = ''
    }, 10000)
    const freshDocs = await fetchDocuments()
    if (freshDocs.length > 0) {
      const newDoc = freshDocs[0]
      selectedDocId.value = newDoc.docId
      selectedDocIds.value = newDoc.docIds
      isLoadingGraph.value = true
      graphError.value = null
      try {
        const response = await getDocumentGraph(newDoc.docIds)
        graphNodes.value = response.nodes
        graphEdges.value = response.edges
      } catch (err) {
        graphError.value = err instanceof Error ? err.message : 'Failed to load document graph'
      } finally {
        isLoadingGraph.value = false
      }
    }
  }
})
</script>
