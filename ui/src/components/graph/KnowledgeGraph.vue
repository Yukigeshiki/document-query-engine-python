<template>
  <div ref="container" class="w-full h-[500px] rounded-lg border border-border bg-card" />
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import cytoscape from 'cytoscape'
import type { Core, LayoutOptions } from 'cytoscape'
import type { SubgraphNode, SubgraphEdge } from '@/types/queryEngine'

const LAYOUT_OPTIONS: LayoutOptions = {
  name: 'cose',
  animate: true,
  animationDuration: 500,
  nodeRepulsion: () => 8000,
  idealEdgeLength: () => 100,
} as LayoutOptions

const props = defineProps<{
  nodes: SubgraphNode[]
  edges: SubgraphEdge[]
}>()

const container = ref<HTMLDivElement | null>(null)
let cy: Core | null = null

function buildElements() {
  const nodeElements = props.nodes.map((node) => ({
    data: {
      id: node.id,
      label: node.id,
    },
  }))

  const edgeElements = props.edges.map((edge, i) => ({
    data: {
      id: `edge-${i}`,
      source: edge.source,
      target: edge.target,
      label: edge.relation,
    },
  }))

  return [...nodeElements, ...edgeElements]
}

function initGraph() {
  if (!container.value) return

  cy = cytoscape({
    container: container.value,
    elements: buildElements(),
    style: [
      {
        selector: 'node',
        style: {
          'background-color': '#6366f1',
          'label': 'data(label)',
          'color': '#e2e8f0',
          'text-valign': 'bottom',
          'text-halign': 'center',
          'font-size': '11px',
          'text-margin-y': 6,
          'width': 30,
          'height': 30,
        },
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#475569',
          'target-arrow-color': '#475569',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(label)',
          'font-size': '9px',
          'color': '#94a3b8',
          'text-rotation': 'autorotate',
          'text-margin-y': -8,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'background-color': '#818cf8',
          'border-width': 2,
          'border-color': '#a5b4fc',
        },
      },
    ],
    layout: LAYOUT_OPTIONS,
    minZoom: 0.3,
    maxZoom: 3,
  })
}

function updateGraph() {
  if (!cy) return
  cy.elements().remove()
  cy.add(buildElements())
  cy.layout(LAYOUT_OPTIONS).run()
}

onMounted(initGraph)

onUnmounted(() => {
  cy?.destroy()
  cy = null
})

watch(
  () => [props.nodes, props.edges],
  () => {
    if (cy) {
      updateGraph()
    }
  },
)
</script>
