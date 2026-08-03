<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { api, readSse } from '../api/client'
import ConversationHistoryDrawer, { type HistoryItem } from '../components/ConversationHistoryDrawer.vue'

const sessions = ref<any[]>([]); const snapshot = ref<any>(); const input = ref(''); const sending = ref(false); const status = ref(''); const streamText = ref(''); const error = ref(''); const chat = ref<HTMLElement>(); const historyOpen = ref(true)
const historyItems = computed<HistoryItem[]>(() => sessions.value.map(item => ({ id: item.thread_id, title: item.title, updatedAt: item.updated_at, deletable: !sending.value })))
async function loadSessions() { sessions.value = await api.service('listing-creation', 'sessions') }
async function createSession() { snapshot.value = await api.service('listing-creation', 'sessions', { method: 'POST' }); localStorage.setItem('creation-session', snapshot.value.state.thread_id); await loadSessions() }
async function loadSession(id: string) { snapshot.value = await api.service('listing-creation', `sessions/${id}`); localStorage.setItem('creation-session', id); streamText.value = ''; await nextTick(); chat.value?.scrollTo(0, chat.value.scrollHeight) }
async function setAsin(value: string) { if (!snapshot.value) return; snapshot.value = await api.service<any>('listing-creation', `sessions/${snapshot.value.state.thread_id}/asin`, { method: 'PATCH', body: JSON.stringify({ asin: value.trim().toUpperCase() }) }); }
async function renameSession(id: string, title: string) { const renamed = await api.service<any>('listing-creation', `sessions/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }); if (snapshot.value?.state.thread_id === id) snapshot.value = renamed; await loadSessions() }
async function deleteSession(id: string) { await api.service('listing-creation', `sessions/${id}`, { method: 'DELETE' }); if (snapshot.value?.state.thread_id === id) { snapshot.value = undefined; input.value = ''; localStorage.removeItem('creation-session') } await loadSessions() }
async function send() {
  const text = input.value.trim(); if (!text || sending.value || !snapshot.value) return
  input.value = ''; sending.value = true; status.value = '已收到消息，Agent 正在响应'; streamText.value = ''; error.value = ''
  snapshot.value.state.messages.push({ role: 'user', content: text, status: 'complete' }); await nextTick(); chat.value?.scrollTo(0, chat.value.scrollHeight)
  try {
    const response = await fetch(api.serviceUrl('listing-creation', `sessions/${snapshot.value.state.thread_id}/messages`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
    await readSse(response, (event, data) => { if (event === 'status') status.value = data.content; else if (event === 'text') { status.value = ''; streamText.value += data.content } else if (event === 'snapshot') snapshot.value = data; else if (event === 'error') error.value = data.message })
    await loadSession(snapshot.value.state.thread_id); await loadSessions()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { sending.value = false; status.value = ''; await loadSessions() }
}
onMounted(async () => { await loadSessions(); const remembered = localStorage.getItem('creation-session'); const target = sessions.value.find(item => item.thread_id === remembered)?.thread_id || sessions.value[0]?.thread_id; if (target) await loadSession(target) })
</script>

<template>
  <section class="page workspace creation-layout" :class="{ 'history-open': historyOpen }">
    <ConversationHistoryDrawer v-model:open="historyOpen" title="Listing 创作" :items="historyItems" :selected-id="snapshot?.state.thread_id" :busy="sending" :show-asin="true" :asin="snapshot?.state.asin" @create="createSession" @select="loadSession" @rename="renameSession" @delete="deleteSession" @asin="setAsin"/>
    <main class="chat-shell glass-panel"><header class="workspace-head"><div><p class="eyebrow">PROMPT DRIVEN · LLM TOOL USE</p><h1>对话式 Listing 创作 Agent</h1></div><div class="stage-pill">自由对话</div></header>
      <div ref="chat" class="chat"><div v-if="!snapshot" class="message assistant"><span class="avatar">AI</span><div class="bubble markdown">从历史抽屉选择一条对话，或点击“＋”新建对话</div></div><template v-for="(message, index) in snapshot?.state.messages || []" :key="index"><div class="message" :class="message.role"><span class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</span><div class="bubble markdown">{{ message.content }}</div></div></template><div v-if="sending" class="message assistant"><span class="avatar">AI</span><div class="bubble markdown"><div v-if="status" class="typing"><i/><i/><i/> {{ status }}</div><template v-else>{{ streamText }}<b class="cursor">▍</b></template></div></div><div v-if="error" class="alert">{{ error }}</div></div>
      <form class="composer" @submit.prevent="send"><textarea v-model="input" :disabled="!snapshot" :placeholder="snapshot ? '粘贴完整资料，或回复确认、修改意见和补充信息' : '请先新建或选择历史对话'" @keydown.enter.exact.prevent="send"/><button class="send" :disabled="sending || !snapshot || !input.trim()">发送</button></form>
    </main>
    <aside class="context-panel glass-panel"><div class="facts"><h3>已确认事实 <span v-if="snapshot?.state.confirmed_facts?.length">{{ snapshot.state.confirmed_facts.length }}</span></h3><p v-if="!snapshot?.state.confirmed_facts?.length" class="muted">对话中明确提供或确认的产品事实会显示在这里</p><div v-for="fact in snapshot?.state.confirmed_facts || []" :key="fact.key" class="fact confirmed"><b class="fact-check">✓</b><div><b>{{ fact.label }}</b><span>{{ fact.value }}</span><small>{{ fact.group }}</small></div></div></div></aside>
  </section>
</template>

<style scoped>
.facts h3 { display: flex; align-items: center; justify-content: space-between; }
.facts h3 span { min-width: 24px; padding: 2px 7px; border-radius: 12px; background: hsl(0 0% 100% / .08); color: hsl(0 0% 100% / .76); font: 10px monospace; text-align: center; }
.fact { grid-template-columns: 22px 1fr; }
.fact-check { color: hsl(0 0% 100% / .76); font-size: 13px; }
.fact small { display: block; color: var(--subtle); font-size: 9px; margin-top: 4px; }
.context-panel { border-radius: 28px; padding: 22px; overflow: auto; }
.context-panel .facts { border-top: 0; margin-top: 0; padding-top: 0; }
</style>
