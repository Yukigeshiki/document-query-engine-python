/** Application router with lazy-loaded views for document upload and KG querying. */
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/upload',
    },
    {
      path: '/upload',
      name: 'upload',
      component: () => import('@/views/UploadView.vue'),
    },
    {
      path: '/query',
      name: 'query',
      component: () => import('@/views/QueryView.vue'),
    },
  ],
})

export default router
