<template>
  <div v-if="sourceNodes.length > 0" class="space-y-2">
    <h3 class="text-sm font-semibold text-muted-foreground">
      {{ sourceNodes.length >= 5 ? 'Top 5 Sources' : 'Top Sources' }}
    </h3>
    <div
      v-for="(node, i) in topSources"
      :key="i"
      class="rounded-md border border-border p-4 space-y-2"
    >
      <div class="flex items-center gap-2">
        <span
          v-if="node.metadata.fileName"
          class="text-xs font-medium truncate"
        >
          {{ node.metadata.fileName }}
        </span>
        <span
          class="text-xs font-medium px-2 py-0.5 rounded-full"
          :class="node.sourceType === 'kg' ? 'bg-violet-500/10 text-violet-500' : 'bg-blue-500/10 text-blue-500'"
        >
          {{ node.sourceType === 'kg' ? 'KG' : 'Vector' }}
        </span>
        <span
          v-if="node.score != null"
          class="text-xs text-muted-foreground"
        >
          {{ formatScore(node) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SourceNodeInfo } from '@/types/queryEngine'

const props = defineProps<{
  sourceNodes: SourceNodeInfo[]
}>()

const topSources = computed(() => props.sourceNodes.slice(0, 5))

function formatScore(node: SourceNodeInfo): string {
  if (node.score == null) return ''
  if (node.sourceType === 'kg') {
    return `score: ${node.score.toFixed(0)}`
  }
  return `similarity: ${Math.round(node.score * 100)}%`
}
</script>
