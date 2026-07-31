<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { api, readSse } from '../api/client'

const sessions = ref<any[]>([]); const snapshot = ref<any>(); const input = ref(''); const sending = ref(false); const status = ref(''); const streamText = ref(''); const error = ref(''); const chat = ref<HTMLElement>()
async function loadSessions() { sessions.value = await api.service('listing-creation', 'sessions'); if (!snapshot.value && sessions.value.length) await loadSession(sessions.value[0].thread_id) }
async function createSession() { snapshot.value = await api.service('listing-creation', 'sessions', { method: 'POST' }); await loadSessions() }
async function loadSession(id: string) { snapshot.value = await api.service('listing-creation', `sessions/${id}`); streamText.value = ''; await nextTick(); chat.value?.scrollTo(0, chat.value.scrollHeight) }
async function send() {
  const text = input.value.trim(); if (!text || sending.value) return
  input.value = ''; sending.value = true; status.value = '已收到消息，Agent 正在响应'; streamText.value = ''; error.value = ''
  snapshot.value.state.messages.push({ role: 'user', content: text, status: 'complete' }); await nextTick(); chat.value?.scrollTo(0, chat.value.scrollHeight)
  try {
    const response = await fetch(api.serviceUrl('listing-creation', `sessions/${snapshot.value.state.thread_id}/messages`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
    await readSse(response, (event, data) => { if (event === 'status') status.value = data.content; else if (event === 'text') { status.value = ''; streamText.value += data.content } else if (event === 'snapshot') snapshot.value = data; else if (event === 'error') error.value = data.message })
    await loadSession(snapshot.value.state.thread_id); await loadSessions()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { sending.value = false; status.value = '' }
}
onMounted(async () => { await loadSessions(); if (!sessions.value.length) await createSession() })
</script>

<template>
  <section class="page workspace creation-layout">
    <aside class="side glass-panel"><div class="side-head"><div><p class="eyebrow">SESSIONS</p><h2>Listing 创作</h2></div><button class="icon-btn" @click="createSession">＋</button></div><button v-for="item in sessions" :key="item.thread_id" class="session" :class="{ selected: snapshot?.state.thread_id === item.thread_id }" @click="loadSession(item.thread_id)">{{ item.title }}</button><div class="facts"><h3>已确认事实 <span v-if="snapshot?.state.confirmed_facts?.length">{{ snapshot.state.confirmed_facts.length }}</span></h3><p v-if="!snapshot?.state.confirmed_facts?.length" class="muted">对话中明确提供或确认的产品事实会显示在这里</p><div v-for="fact in snapshot?.state.confirmed_facts || []" :key="fact.key" class="fact confirmed"><b class="fact-check">✓</b><div><b>{{ fact.label }}</b><span>{{ fact.value }}</span><small>{{ fact.group }}</small></div></div></div></aside>
    <main class="chat-shell glass-panel"><header class="workspace-head"><div><p class="eyebrow">PROMPT DRIVEN · LLM TOOL USE</p><h1>对话式 Listing 创作 Agent</h1></div><div class="stage-pill">自由对话</div></header>
      <div ref="chat" class="chat"><template v-for="(message, index) in snapshot?.state.messages || []" :key="index"><div class="message" :class="message.role"><span class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</span><div class="bubble markdown">{{ message.content }}</div></div></template><div v-if="sending" class="message assistant"><span class="avatar">AI</span><div class="bubble markdown"><div v-if="status" class="typing"><i/><i/><i/> {{ status }}</div><template v-else>{{ streamText }}<b class="cursor">▍</b></template></div></div><div v-if="error" class="alert">{{ error }}</div></div>
      <form class="composer" @submit.prevent="send"><textarea v-model="input" placeholder="粘贴完整资料，或回复确认、修改意见和补充信息" @keydown.enter.exact.prevent="send"/><button class="send" :disabled="sending || !input.trim()">发送</button></form>
    </main>
  </section>
</template>

<style scoped>
.facts h3 { display: flex; align-items: center; justify-content: space-between; }
.facts h3 span { min-width: 24px; padding: 2px 7px; border-radius: 12px; background: rgba(67, 223, 252, .1); color: var(--cyan); font: 10px monospace; text-align: center; }
.fact { grid-template-columns: 22px 1fr; }
.fact-check { color: #63e6b5; font-size: 13px; }
.fact small { display: block; color: #456779; font-size: 9px; margin-top: 4px; }
</style>
