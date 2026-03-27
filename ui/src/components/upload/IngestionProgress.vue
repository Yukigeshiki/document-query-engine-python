<template>
  <div class="rounded-lg border border-border p-6">
    <!-- Uploading -->
    <div v-if="status === 'uploading'" class="flex items-center gap-3">
      <Loader2 class="h-5 w-5 animate-spin text-primary" />
      <span class="text-sm font-medium">Uploading file...</span>
    </div>

    <!-- Processing -->
    <div v-else-if="status === 'pending' || status === 'started'" class="flex flex-col gap-2">
      <div class="flex items-center gap-3">
        <Loader2 class="h-5 w-5 animate-spin text-primary" />
        <span class="text-sm font-medium">
          {{ status === 'pending' ? 'Queued for processing...' : 'Extracting knowledge graph...' }}
        </span>
      </div>
      <p v-if="taskId" class="text-xs text-muted-foreground">
        Task: {{ taskId }}
      </p>
    </div>

    <!-- Success -->
    <div v-else-if="status === 'success' && result" class="flex flex-col gap-2">
      <div class="flex items-center gap-3">
        <CheckCircle2 class="h-5 w-5 text-green-500" />
        <span class="text-sm font-medium">Ingestion complete</span>
      </div>
      <div class="flex gap-4 text-xs text-muted-foreground">
        <span>{{ result.totalDocuments }} document(s)</span>
        <span>{{ result.totalTriplets }} triplets extracted</span>
      </div>
      <div v-if="result.errors.length > 0" class="mt-2">
        <p
          v-for="(err, i) in result.errors"
          :key="i"
          class="text-xs text-destructive"
        >
          {{ err }}
        </p>
      </div>
    </div>

    <!-- Failure -->
    <div v-else-if="status === 'failure'" class="flex flex-col gap-2">
      <div class="flex items-center gap-3">
        <XCircle class="h-5 w-5 text-destructive" />
        <span class="text-sm font-medium">Ingestion failed</span>
      </div>
      <p v-if="error" class="text-xs text-destructive">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CheckCircle2, Loader2, XCircle } from 'lucide-vue-next'
import type { IngestResult } from '@/types/queryEngine'
import type { UploadStatus } from '@/composables/useFileUpload'

defineProps<{
  status: UploadStatus
  taskId: string | null
  result: IngestResult | null
  error: string | null
}>()
</script>
