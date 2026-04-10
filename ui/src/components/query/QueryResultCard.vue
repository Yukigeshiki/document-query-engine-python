<template>
  <div class="rounded-lg border border-border p-6">
    <div class="flex items-start gap-3">
      <MessageSquare class="h-5 w-5 text-primary shrink-0 mt-0.5" />
      <p class="text-sm leading-relaxed whitespace-pre-wrap">
        {{ response }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MessageSquare } from 'lucide-vue-next'

defineProps<{
  response: string
}>()
</script>
