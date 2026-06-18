import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/Login.vue'),
    },
    {
      path: '/',
      name: 'upload',
      component: () => import('@/views/UploadResume.vue'),
    },
    {
      path: '/interview',
      name: 'interview',
      component: () => import('@/views/Interview.vue'),
    },
    {
      path: '/report',
      name: 'report',
      component: () => import('@/views/ViewReport.vue'),
    },
  ],
})

export default router
