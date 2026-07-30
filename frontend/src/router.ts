import { createRouter, createWebHistory } from 'vue-router'
import DashboardPage from './pages/DashboardPage.vue'
import CreationPage from './pages/CreationPage.vue'
import OptimizationPage from './pages/OptimizationPage.vue'
import { api } from './api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: DashboardPage },
    { path: '/agents/listing-creation', component: CreationPage, meta: { agent: 'listing-creation' } },
    { path: '/agents/listing-optimization', component: OptimizationPage, meta: { agent: 'listing-optimization' } },
  ],
})

router.beforeEach(async (to) => {
  const agent = to.meta.agent
  if (typeof agent !== 'string') return true
  try {
    const status = await api.getAgent(agent)
    if (status.status === 'running') return true
  } catch { /* dashboard displays connection errors */ }
  return { path: '/', query: { start: agent } }
})

export default router
