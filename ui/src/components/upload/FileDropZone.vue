<template>
  <div
    :class="[
      'border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors',
      isDragging ? 'border-primary bg-accent' : 'border-border hover:border-primary/50',
    ]"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="onDrop"
    @click="openFilePicker"
  >
    <input
      ref="fileInput"
      type="file"
      :accept="ACCEPTED_EXTENSIONS"
      class="hidden"
      @change="onFileSelected"
    >

    <div
      v-if="!selectedFile"
      class="flex flex-col items-center gap-3"
    >
      <Upload class="h-10 w-10 text-muted-foreground" />
      <p class="text-sm font-medium">
        Drag & drop a file here, or click to browse
      </p>
      <p class="text-xs text-muted-foreground">
        PDF, DOCX, or TXT — max 5MB
      </p>
    </div>

    <div
      v-else
      class="flex flex-col items-center gap-3"
    >
      <FileText class="h-10 w-10 text-primary" />
      <p class="text-sm font-medium">
        {{ selectedFile.name }}
      </p>
      <p class="text-xs text-muted-foreground">
        {{ formatFileSize(selectedFile.size) }}
      </p>
    </div>

    <p
      v-if="validationError"
      class="mt-3 text-sm text-destructive"
    >
      {{ validationError }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Upload, FileText } from 'lucide-vue-next'

const ACCEPTED_EXTENSIONS = '.pdf,.docx,.txt'
const MAX_FILE_SIZE = 5 * 1024 * 1024 // 5MB

const emit = defineEmits<{
  'file-selected': [file: File]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const selectedFile = ref<File | null>(null)
const validationError = ref<string | null>(null)

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function validateFile(file: File): boolean {
  validationError.value = null

  const parts = file.name.split('.')
  const ext = parts.length > 1 ? '.' + parts.pop()!.toLowerCase() : ''
  if (!['.pdf', '.docx', '.txt'].includes(ext)) {
    validationError.value = `Unsupported file type: ${ext}. Use PDF, DOCX, or TXT.`
    return false
  }

  if (file.size > MAX_FILE_SIZE) {
    validationError.value = `File too large (${formatFileSize(file.size)}). Max 20MB.`
    return false
  }

  return true
}

function selectFile(file: File) {
  if (validateFile(file)) {
    selectedFile.value = file
    emit('file-selected', file)
  }
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const file = event.dataTransfer?.files[0]
  if (file) selectFile(file)
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) selectFile(file)
}

function openFilePicker() {
  fileInput.value?.click()
}
</script>
