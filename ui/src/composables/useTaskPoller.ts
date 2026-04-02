/**
 * Composable for polling a background task until it reaches a terminal state.
 *
 * Uses setTimeout recursion (not setInterval) to avoid stacking concurrent
 * requests when a poll takes longer than the interval. Includes a max-attempts
 * guard to prevent infinite polling if a task gets stuck.
 */

import { getTaskStatus } from '@/services/queryEngine'
import type { TaskStatusResponse } from '@/types/queryEngine'

const POLL_INTERVAL_MS = 2000
const MAX_POLL_ATTEMPTS = 120 // 4 minutes at 2s intervals

export interface TaskPollerCallbacks {
  /** Called on each poll with the latest status. */
  onStatus?: (status: TaskStatusResponse) => void
}

/**
 * Poll a task until it reaches a terminal state.
 *
 * @param taskId - The task ID to poll.
 * @param callbacks - Optional callbacks for status updates.
 * @returns The final task status response.
 * @throws Error if the task fails, is revoked, or polling times out.
 */
export function pollTask(
  taskId: string,
  callbacks?: TaskPollerCallbacks,
): { promise: Promise<TaskStatusResponse>; cancel: () => void } {
  let cancelled = false
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  const cancel = () => {
    cancelled = true
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  const promise = new Promise<TaskStatusResponse>((resolve, reject) => {
    let attempts = 0

    const poll = async () => {
      if (cancelled) return

      if (++attempts > MAX_POLL_ATTEMPTS) {
        reject(new Error('Task polling timed out'))
        return
      }

      try {
        const taskStatus = await getTaskStatus(taskId)
        callbacks?.onStatus?.(taskStatus)

        if (taskStatus.status === 'success') {
          resolve(taskStatus)
        } else if (taskStatus.status === 'failure' || taskStatus.status === 'revoked') {
          reject(new Error(taskStatus.error || 'Task failed'))
        } else {
          timeoutId = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (err) {
        reject(err)
      }
    }

    timeoutId = setTimeout(poll, POLL_INTERVAL_MS)
  })

  return { promise, cancel }
}
