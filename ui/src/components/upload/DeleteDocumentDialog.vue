<template>
  <AlertDialog :open="doc !== null" @update:open="onOpenChange">
    <AlertDialogContent>
      <AlertDialogTitle>Delete document</AlertDialogTitle>
      <AlertDialogDescription>
        Are you sure you want to delete
        <span class="font-medium">{{ doc?.fileName || doc?.docId }}</span>?
        This will remove it from all storage layers and cannot be undone.
      </AlertDialogDescription>
      <div class="flex justify-end gap-3 mt-2">
        <AlertDialogCancel>Cancel</AlertDialogCancel>
        <AlertDialogAction @click="onConfirm">Delete</AlertDialogAction>
      </div>
    </AlertDialogContent>
  </AlertDialog>
</template>

<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type { DocumentInfo } from '@/types/queryEngine'

const props = defineProps<{
  doc: DocumentInfo | null
}>()

const emit = defineEmits<{
  'update:doc': [value: null]
  confirm: [doc: DocumentInfo]
}>()

function onConfirm() {
  if (props.doc) {
    emit('confirm', props.doc)
  }
}

function onOpenChange(open: boolean) {
  if (!open) {
    emit('update:doc', null)
  }
}
</script>
