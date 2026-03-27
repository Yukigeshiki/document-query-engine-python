/** Composable providing shared sidebar expand/collapse state with localStorage persistence. */
import { ref } from 'vue'

const STORAGE_KEY = 'sidebar-expanded'

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Ignore — private browsing or quota exceeded
  }
}

// Module-level refs: intentional singleton so all consumers share the same sidebar state
const isExpanded = ref(readStorage(STORAGE_KEY) === 'true')

export function useSidebar() {
  function toggle() {
    isExpanded.value = !isExpanded.value
    writeStorage(STORAGE_KEY, String(isExpanded.value))
  }

  return {
    isExpanded,
    toggle,
  }
}
