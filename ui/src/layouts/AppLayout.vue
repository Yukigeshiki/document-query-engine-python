<template>
  <div class="min-h-screen bg-background">
    <AppSidebar />

    <main
      :class="[
        'px-16 py-8 transition-all duration-300 ease-in-out',
        isExpanded ? 'ml-64' : 'ml-16'
      ]"
    >
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { AppSidebar } from '@/components/layout'
import { useSidebar } from '@/composables/ui'

const { isExpanded } = useSidebar()
</script>
