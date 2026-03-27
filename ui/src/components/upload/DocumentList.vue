<template>
  <div v-if="documents.length > 0" class="space-y-2">
    <h2 class="text-lg font-semibold">Uploaded Documents</h2>
    <div class="space-y-1">
      <button
        v-for="doc in documents"
        :key="doc.docId"
        @click="$emit('select-document', doc)"
        :class="[
          'w-full flex items-center justify-between px-4 py-3 rounded-md border text-left transition-colors cursor-pointer',
          selectedId === doc.docId
            ? 'border-primary bg-accent'
            : 'border-border hover:bg-accent/50',
        ]"
      >
        <span class="flex items-center gap-3 min-w-0">
          <FileText class="h-4 w-4 shrink-0 text-muted-foreground" />
          <span class="min-w-0">
            <span class="block text-sm font-medium truncate">{{ doc.fileName || doc.docId }}</span>
            <span class="block text-xs text-muted-foreground">
              {{ doc.nodeCount }} node(s)
            </span>
          </span>
        </span>
      </button>
    </div>

    <button
      v-if="hasMore"
      @click="$emit('load-more')"
      :disabled="isLoading"
      class="w-full py-2 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
    >
      {{ isLoading ? 'Loading...' : 'Load more' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { FileText } from 'lucide-vue-next'
import type { DocumentInfo } from '@/types/queryEngine'

defineProps<{
  documents: DocumentInfo[]
  selectedId: string | null
  hasMore: boolean
  isLoading: boolean
}>()

defineEmits<{
  'select-document': [doc: DocumentInfo]
  'load-more': []
}>()
</script>
