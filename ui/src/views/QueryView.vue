<template>
  <AppLayout>
    <div class="max-w-6xl mx-auto space-y-6">
      <div>
        <h1 class="text-2xl font-bold">Query Your Documents</h1>
        <p class="text-muted-foreground mt-1">
          Ask questions about the data in your documents.
        </p>
      </div>

      <!-- Query input -->
      <div class="flex gap-2">
        <input
          v-model="query"
          placeholder="Ask a question..."
          class="flex-1 px-3 py-2 border border-input rounded-md text-sm bg-background"
          :disabled="isLoading"
          @keydown.enter="submitQuery"
        />
        <Select v-model="retrievalMode" :disabled="isLoading">
          <SelectTrigger class="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="dual">Dual</SelectItem>
            <SelectItem value="kg_only">KG Only</SelectItem>
            <SelectItem value="vector_only">Vector Only</SelectItem>
          </SelectContent>
        </Select>
        <button
          @click="submitQuery"
          :disabled="!query.trim() || isLoading"
          class="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          Ask
        </button>
      </div>

      <!-- Loading -->
      <div v-if="isLoading" class="flex items-center gap-3 rounded-lg border border-border p-6">
        <Loader2 class="h-5 w-5 animate-spin text-primary" />
        <span class="text-sm font-medium">Querying knowledge graph...</span>
      </div>

      <!-- Error -->
      <p v-if="error" class="text-sm text-destructive">
        {{ error }}
      </p>

      <!-- Results -->
      <template v-if="result">
        <QueryResultCard :response="result.response" />
        <SourceNodeList :source-nodes="result.sourceNodes" />
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import AppLayout from '@/layouts/AppLayout.vue'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import QueryResultCard from '@/components/query/QueryResultCard.vue'
import SourceNodeList from '@/components/query/SourceNodeList.vue'
import { queryKnowledgeGraph } from '@/services/queryEngine'
import type { QueryResponse, RetrievalMode } from '@/types/queryEngine'

const query = ref('')
const retrievalMode = ref<RetrievalMode>('dual')
const isLoading = ref(false)
const error = ref<string | null>(null)
const result = ref<QueryResponse | null>(null)

async function submitQuery() {
  if (!query.value.trim() || isLoading.value) return

  isLoading.value = true
  error.value = null
  result.value = null

  try {
    result.value = await queryKnowledgeGraph(query.value.trim(), retrievalMode.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Query failed'
  } finally {
    isLoading.value = false
  }
}
</script>
