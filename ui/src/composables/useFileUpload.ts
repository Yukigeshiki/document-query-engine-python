/**
 * Composable managing the file upload → task polling → completion lifecycle.
 *
 * Uploads a file, then polls the task status until the task reaches a
 * terminal state (success, failure, or revoked).
 */

import { ref, onUnmounted } from 'vue'
import { uploadDocument } from '@/services/queryEngine'
import { pollTask } from '@/composables/useTaskPoller'
import type { IngestResult } from '@/types/queryEngine'

export type UploadStatus = 'idle' | 'uploading' | 'pending' | 'started' | 'success' | 'failure'

export function useFileUpload() {
  const file = ref<File | null>(null)
  const taskId = ref<string | null>(null)
  const status = ref<UploadStatus>('idle')
  const result = ref<IngestResult | null>(null)
  const error = ref<string | null>(null)

  let cancelPoller: (() => void) | null = null

  function stopPolling() {
    if (cancelPoller !== null) {
      cancelPoller()
      cancelPoller = null
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

      const poller = pollTask(response.taskId, {
        onStatus: (taskStatus) => {
          status.value = taskStatus.status as UploadStatus
        },
      })
      cancelPoller = poller.cancel

      const finalStatus = await poller.promise
      result.value = finalStatus.result as IngestResult
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Upload failed'
      status.value = 'failure'
    } finally {
      cancelPoller = null
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
