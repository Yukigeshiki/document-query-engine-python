<template>
  <div
    v-if="documents.length > 0"
    class="space-y-2"
  >
    <h2 class="text-lg font-semibold">
      Uploaded Documents
    </h2>
    <div class="space-y-1">
      <template
        v-for="doc in documents"
        :key="doc.docId"
      >
        <slot
          v-if="selectedId === doc.docId"
          name="above-selected"
        />
        <button
          :disabled="deletingId === doc.docId"
          :class="[
            'group relative w-full flex items-center justify-between px-4 py-3 rounded-md border text-left transition-colors',
            deletingId === doc.docId
              ? 'opacity-50 cursor-not-allowed'
              : 'cursor-pointer',
            selectedId === doc.docId
              ? 'border-primary bg-accent'
              : 'border-border hover:bg-accent/50',
          ]"
          @click="$emit('select-document', doc)"
        >
          <span class="flex items-center gap-3 min-w-0">
            <Loader2
              v-if="deletingId === doc.docId"
              class="h-4 w-4 shrink-0 animate-spin text-muted-foreground"
            />
            <FileText
              v-else
              class="h-4 w-4 shrink-0 text-muted-foreground"
            />
            <span class="min-w-0">
              <span class="block text-sm font-medium truncate">
                {{ deletingId === doc.docId ? `Deleting ${doc.fileName || doc.docId}...` : (doc.fileName || doc.docId) }}
              </span>
              <span class="block text-xs text-muted-foreground">
                {{ doc.nodeCount }} node(s)
              </span>
            </span>
          </span>
          <span
            v-if="deletingId !== doc.docId"
            class="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
            title="Delete document"
            @click.stop="$emit('delete-document', doc)"
          >
            <Trash2 class="h-3.5 w-3.5" />
          </span>
        </button>
      </template>
    </div>

    <button
      v-if="hasMore"
      :disabled="isLoading"
      class="w-full py-2 text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
      @click="$emit('load-more')"
    >
      {{ isLoading ? 'Loading...' : 'Load more' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { FileText, Loader2, Trash2 } from 'lucide-vue-next'
import type { DocumentInfo } from '@/types/queryEngine'

defineProps<{
  documents: DocumentInfo[]
  selectedId: string | null
  deletingId: string | null
  hasMore: boolean
  isLoading: boolean
}>()

defineEmits<{
  'select-document': [doc: DocumentInfo]
  'delete-document': [doc: DocumentInfo]
  'load-more': []
}>()
</script>
