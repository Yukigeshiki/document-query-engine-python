/** Shared utility functions for class merging and date formatting. */
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merges Tailwind CSS classes with conflict resolution via clsx + tailwind-merge.
 *
 * @param inputs - Class values to merge (strings, arrays, objects).
 * @returns The merged class string with Tailwind conflicts resolved.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Formats an ISO date string to en-GB locale with date and time.
 *
 * @param dateString - An ISO 8601 date string, or undefined.
 * @returns The formatted date string, or '-' if the input is undefined.
 */
export function formatDate(dateString: string | undefined): string {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
