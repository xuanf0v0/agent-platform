<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentSettings from '../components/AgentSettings.vue'
import { useAgentStore } from '../stores/agents'
import type { AgentInfo } from '../types'

const store = useAgentStore(); const route = useRoute(); const router = useRouter(); const expanded = ref('')
const running = computed(() => store.agents.filter(agent => agent.status === 'running').length)
onMounted(async () => { await store.load(); if (typeof route.query.start === 'string') expanded.value = route.query.start })
async function open(agent: AgentInfo) { if (agent.status !== 'running') { await store.toggle(agent); if (store.error) return } await router.push(`/agents/${agent.id}`) }
</script>

<template>
  <section class="page dashboard">
    <header class="hero glass-panel"><div><p class="eyebrow">AMAZON INTELLIGENCE PLATFORM</p><h1>Agent Control Center</h1><p>统一管理 Listing 智能体、运行状态与工作空间</p></div><button class="btn ghost" :disabled="store.loading" @click="store.load">{{ store.loading ? '同步中…' : '同步状态' }}</button></header>
    <div class="metrics"><article class="glass-panel"><span>智能体总数</span><strong>{{ store.agents.length.toString().padStart(2, '0') }}</strong><small>REGISTERED AGENTS</small></article><article class="glass-panel active"><span>正在运行</span><strong>{{ running.toString().padStart(2, '0') }}</strong><small>● SYSTEM ACTIVE</small></article><article class="glass-panel"><span>可用容量</span><strong>{{ (store.agents.length - running).toString().padStart(2, '0') }}</strong><small>AVAILABLE CAPACITY</small></article></div>
    <div v-if="store.error" class="alert">连接失败：{{ store.error }}</div>
    <div class="section-title"><div><p class="eyebrow">DEPLOYMENT WORKSPACE</p><h2>智能体服务</h2></div></div>
    <div class="agent-grid">
      <article v-for="agent in store.agents" :key="agent.id" class="agent-card glass-panel">
        <div class="agent-head"><div class="agent-icon">{{ agent.icon }}</div><span class="status" :class="agent.status"><i />{{ agent.status }}</span></div>
        <h3>{{ agent.name }}</h3><p>{{ agent.description }}</p>
        <div class="agent-meta"><span>PORT {{ agent.port }}</span><span v-if="agent.pid">PID {{ agent.pid }}</span></div>
        <div class="agent-actions"><button class="btn primary" @click="open(agent)">{{ agent.status === 'running' ? '进入工作台' : '启动并进入' }}</button><button v-if="agent.status === 'running'" class="btn danger" @click="store.toggle(agent)">停止</button><button class="btn ghost" @click="expanded = expanded === agent.id ? '' : agent.id">设置</button></div>
        <AgentSettings v-if="expanded === agent.id" :agent-id="agent.id" :running="agent.status === 'running'" />
      </article>
    </div>
  </section>
</template>
