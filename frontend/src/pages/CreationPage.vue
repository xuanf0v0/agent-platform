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
async function factAction(fact: any, action: 'confirm' | 'revise') { const id = snapshot.value.state.thread_id; if (action === 'revise') { const value = prompt(`修改 ${fact.label_zh}`, fact.value); if (value === null) return; snapshot.value = await api.service('listing-creation', `sessions/${id}/facts/${fact.fact_id}`, { method: 'PUT', body: JSON.stringify({ value }) }) } else snapshot.value = await api.service('listing-creation', `sessions/${id}/facts/${fact.fact_id}/confirm`, { method: 'POST' }) }
onMounted(async () => { await loadSessions(); if (!sessions.value.length) await createSession() })
</script>

<template>
  <section class="page workspace creation-layout">
    <aside class="side glass-panel"><div class="side-head"><div><p class="eyebrow">SESSIONS</p><h2>Listing 创作</h2></div><button class="icon-btn" @click="createSession">＋</button></div><button v-for="item in sessions" :key="item.thread_id" class="session" :class="{ selected: snapshot?.state.thread_id === item.thread_id }" @click="loadSession(item.thread_id)">{{ item.title }}</button><div class="facts"><h3>已确认事实</h3><template v-if="snapshot"><div v-for="fact in snapshot.state.candidates" :key="fact.fact_id" class="fact" :class="{ confirmed: fact.status === 'confirmed' || fact.status === 'confirmed_missing' }"><button @click="factAction(fact, 'confirm')">{{ fact.status === 'confirmed' || fact.status === 'confirmed_missing' ? '✓' : '○' }}</button><div><b>{{ fact.label_zh }}</b><span>{{ fact.value || '待确认' }}</span></div><button class="edit" @click="factAction(fact, 'revise')">编辑</button></div></template></div></aside>
    <main class="chat-shell glass-panel"><header class="workspace-head"><div><p class="eyebrow">HUMAN VERIFIED · REACT ASSISTED</p><h1>对话式 Listing 创作 Agent</h1></div><div v-if="snapshot" class="stage-pill">{{ snapshot.state.creation_session?.stage }} · facts v{{ snapshot.state.facts_revision }}</div></header>
      <div ref="chat" class="chat"><template v-for="(message, index) in snapshot?.state.messages || []" :key="index"><div class="message" :class="message.role"><span class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</span><div class="bubble markdown">{{ message.content }}</div></div></template><div v-if="sending" class="message assistant"><span class="avatar">AI</span><div class="bubble markdown"><div v-if="status" class="typing"><i/><i/><i/> {{ status }}</div><template v-else>{{ streamText }}<b class="cursor">▍</b></template></div></div><div v-if="error" class="alert">{{ error }}</div></div>
      <form class="composer" @submit.prevent="send"><textarea v-model="input" placeholder="粘贴完整资料，或回复确认、修改意见和补充信息" @keydown.enter.exact.prevent="send"/><button class="send" :disabled="sending || !input.trim()">发送</button></form>
    </main>
  </section>
</template>
