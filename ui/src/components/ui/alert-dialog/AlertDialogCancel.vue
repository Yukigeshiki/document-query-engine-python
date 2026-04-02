<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { AlertDialogCancel } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <AlertDialogCancel
    :class="cn(
      'inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors',
      props.class,
    )"
  >
    <slot />
  </AlertDialogCancel>
</template>
