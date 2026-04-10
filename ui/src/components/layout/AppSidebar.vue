<template>
  <aside
    :class="[
      'fixed left-0 top-0 h-screen bg-card border-r border-border transition-all duration-300 ease-in-out z-40',
      isExpanded ? 'w-64' : 'w-16'
    ]"
  >
    <!-- Logo and toggle section -->
    <div class="flex flex-col items-center px-4 pt-4 pb-2 gap-4">
      <div class="w-16 h-16 rounded-md flex items-center justify-center">
        <Network class="h-8 w-8 text-primary" />
      </div>

      <button
        class="p-2 rounded-md hover:bg-accent transition-colors cursor-pointer"
        :aria-label="isExpanded ? 'Collapse sidebar' : 'Expand sidebar'"
        @click="toggleSidebar"
      >
        <ChevronLeft
          v-if="isExpanded"
          class="h-5 w-5"
        />
        <ChevronRight
          v-else
          class="h-5 w-5"
        />
      </button>
    </div>

    <!-- Navigation items -->
    <nav class="flex flex-col gap-1 px-2 pt-4 pb-2">
      <router-link
        v-for="item in navItems"
        :key="item.label"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-accent transition-colors cursor-pointer"
        active-class="bg-accent"
      >
        <component
          :is="item.icon"
          class="h-5 w-5 shrink-0"
        />
        <span
          v-if="isExpanded"
          class="text-sm font-medium whitespace-nowrap"
        >
          {{ item.label }}
        </span>
      </router-link>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { type Component } from 'vue'
import { useSidebar } from '@/composables/ui'
import {
  ChevronLeft,
  ChevronRight,
  Network,
  Search,
  Upload,
} from 'lucide-vue-next'

interface NavItem {
  path: string
  label: string
  icon: Component
}

const { isExpanded, toggle } = useSidebar()

const navItems: NavItem[] = [
  {
    path: '/query',
    label: 'Query KG',
    icon: Search,
  },
  {
    path: '/upload',
    label: 'Upload Document',
    icon: Upload,
  },
]

function toggleSidebar() {
  toggle()
}
</script>
