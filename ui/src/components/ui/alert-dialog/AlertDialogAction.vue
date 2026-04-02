<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { AlertDialogAction } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <AlertDialogAction
    :class="cn(
      'inline-flex items-center justify-center rounded-md bg-destructive px-4 py-2 text-sm font-medium text-white hover:bg-destructive/90 transition-colors',
      props.class,
    )"
  >
    <slot />
  </AlertDialogAction>
</template>
