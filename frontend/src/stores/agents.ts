import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { AgentInfo } from '../types'

export const useAgentStore = defineStore('agents', () => {
  const agents = ref<AgentInfo[]>([])
  const loading = ref(false)
  const error = ref('')

  async function load() {
    loading.value = true; error.value = ''
    try { agents.value = await api.listAgents() }
    catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
    finally { loading.value = false }
  }
  async function toggle(agent: AgentInfo) {
    loading.value = true; error.value = ''
    try {
      if (agent.status === 'running') await api.stopAgent(agent.id)
      else await api.startAgent(agent.id)
      await load()
    } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); loading.value = false }
  }
  return { agents, loading, error, load, toggle }
})
