/**
 * Composable managing the file upload → task polling → completion lifecycle.
 *
 * Uploads a file, then polls the task status every 2 seconds until
 * the task reaches a terminal state (success, failure, or revoked).
 */

import { ref, onUnmounted } from 'vue'
import { uploadDocument, getTaskStatus } from '@/services/queryEngine'
import type { IngestResult } from '@/types/queryEngine'

export type UploadStatus = 'idle' | 'uploading' | 'pending' | 'started' | 'success' | 'failure'

const POLL_INTERVAL_MS = 2000

export function useFileUpload() {
  const file = ref<File | null>(null)
  const taskId = ref<string | null>(null)
  const status = ref<UploadStatus>('idle')
  const result = ref<IngestResult | null>(null)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function pollTaskStatus() {
    if (!taskId.value) return

    try {
      const taskStatus = await getTaskStatus(taskId.value)
      status.value = taskStatus.status as UploadStatus

      if (taskStatus.status === 'success') {
        result.value = taskStatus.result
        stopPolling()
      } else if (taskStatus.status === 'failure' || taskStatus.status === 'revoked') {
        error.value = taskStatus.error || 'Task failed'
        status.value = 'failure'
        stopPolling()
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to check task status'
      status.value = 'failure'
      stopPolling()
    }
  }

  async function upload() {
    if (!file.value) return

    status.value = 'uploading'
    error.value = null
    result.value = null

    try {
      const response = await uploadDocument(file.value)
      taskId.value = response.taskId
      status.value = 'pending'

      pollTimer = setInterval(pollTaskStatus, POLL_INTERVAL_MS)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Upload failed'
      status.value = 'failure'
    }
  }

  function reset() {
    stopPolling()
    file.value = null
    taskId.value = null
    status.value = 'idle'
    result.value = null
    error.value = null
  }

  onUnmounted(stopPolling)

  return {
    file,
    taskId,
    status,
    result,
    error,
    upload,
    reset,
  }
}
