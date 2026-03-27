/**
 * API client for communicating with the query engine backend.
 *
 * Uses the fetch adapter for native browser fetch support.
 * Sends a Request-ID header for end-to-end request tracing.
 * Transforms undefined values to null for proper JSON serialization.
 */

import axios from 'axios'

const API_TIMEOUT = 30000

const API_URL = import.meta.env.VITE_QUERY_ENGINE_URL || 'http://localhost:8000'

/**
 * Recursively transforms undefined values to null in an object.
 *
 * JavaScript/Vue idiomatically uses undefined for "no value", but JSON.stringify
 * strips undefined values entirely. The backend needs explicit null to know when
 * a field should be cleared.
 */
function transformUndefinedToNull<T>(obj: T): T {
  if (obj === undefined) {
    return null as T
  }

  if (obj === null || typeof obj !== 'object') {
    return obj
  }

  if (Array.isArray(obj)) {
    return obj.map(item => transformUndefinedToNull(item)) as T
  }

  const result: Record<string, unknown> = {}
  for (const key of Object.keys(obj)) {
    const value = (obj as Record<string, unknown>)[key]
    result[key] = value === undefined ? null : transformUndefinedToNull(value)
  }
  return result as T
}

export const apiClient = axios.create({
  baseURL: API_URL,
  timeout: API_TIMEOUT,
  adapter: 'fetch',
  headers: {
    'Content-Type': 'application/json',
  },
  paramsSerializer: {
    indexes: null, // Serialize arrays as ?key=a&key=b (FastAPI style), not ?key[]=a&key[]=b
  },
})

apiClient.interceptors.request.use(
  (config) => {
    if (!config.headers['Request-ID']) {
      config.headers['Request-ID'] = crypto.randomUUID()
    }

    // Let the browser set Content-Type with boundary for FormData uploads
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    } else if (config.data && typeof config.data === 'object') {
      config.data = transformUndefinedToNull(config.data)
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  },
)

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { data, status } = error.response
      const errorMessage = data?.detail || data?.message || data?.title || 'An unexpected error occurred'
      console.error(`[API] Request failed with status ${status}:`, errorMessage)
      const enhancedError = new Error(errorMessage) as Error & { status: number }
      enhancedError.status = status
      return Promise.reject(enhancedError)
    }

    if (error.request) {
      console.error('[API] No response from server')
      return Promise.reject(new Error('No response from server. Please check your connection.'))
    }

    console.error('[API] Request setup failed:', error)
    return Promise.reject(new Error('Request failed. Please try again.'))
  },
)
