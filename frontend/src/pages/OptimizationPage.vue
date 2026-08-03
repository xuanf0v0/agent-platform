<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { api, readSse } from '../api/client'
import ConversationHistoryDrawer, { type HistoryItem } from '../components/ConversationHistoryDrawer.vue'
import DiagnosisReport from '../components/DiagnosisReport.vue'
import OptimizationWorkflowMessage from '../components/OptimizationWorkflowMessage.vue'

const source = ref(''); const run = ref<any>(); const runs = ref<any[]>([]); const input = ref(''); const pendingMessage = ref(''); const processing = ref(false); const progress = ref(''); const progressStep = ref(0); const progressTotal = ref(8); const rounds = ref<any[]>([]); const error = ref(''); const historyOpen = ref(true); const chat = ref<HTMLElement>()
const result = computed(() => run.value?.result); const status = computed(() => run.value?.status || 'idle')
const chatEnabled = computed(() => Boolean(run.value?.chat_enabled && status.value === 'completed'))
const historyItems = computed<HistoryItem[]>(() => runs.value.map(item => ({ id: item.run_id, title: item.title, status: item.status, updatedAt: item.updated_at, deletable: item.status !== 'running' && item.status !== 'queued' })))
async function loadRuns() { runs.value = await api.service('listing-optimization', 'runs') }
async function loadRun(id: string) { run.value = await api.service('listing-optimization', `runs/${id}`); source.value = run.value.source_text; input.value = ''; pendingMessage.value = ''; rounds.value = []; progress.value = ''; error.value = ''; localStorage.setItem('optimization-run', id); if (run.value.status === 'running' || run.value.status === 'queued') await watch(id) }
async function showProcessing(message?: string) { processing.value = true; error.value = ''; if (message) progress.value = message; await nextTick(); chat.value?.scrollTo(0, chat.value.scrollHeight) }
function failProcessing(cause: unknown) { error.value = cause instanceof Error ? cause.message : String(cause); processing.value = false }
async function watch(runId: string, after = -1) {
  await showProcessing(progress.value || 'Agent 正在处理')
  try {
    const response = await fetch(`${api.serviceUrl('listing-optimization', `runs/${runId}/events`)}?after=${after}`)
    await readSse(response, (event, data) => {
      if (event === 'progress' || event === 'status') { progress.value = data.content; progressStep.value = data.step ?? progressStep.value; progressTotal.value = data.total ?? progressTotal.value }
      if (event === 'quality') rounds.value = [...rounds.value.filter(item => item.attempt !== data.attempt), data].sort((a, b) => a.attempt - b.attempt)
      if (event === 'result') run.value = { ...run.value, status: data.status, result: data.result }
      if (event === 'chat_status') progress.value = data.content
      if (event === 'chat_result') run.value = { ...run.value, status: 'completed', result: data.result, turn_status: 'idle' }
      if (event === 'chat_error') error.value = data.message
    })
    run.value = await api.service('listing-optimization', `runs/${runId}`); localStorage.setItem('optimization-run', runId); await loadRuns()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { processing.value = false }
}
async function submit() {
  const text = input.value.trim(); if (!text || processing.value) return
  source.value = text; input.value = ''; rounds.value = []; progress.value = '已接收 Listing，开始处理…'
  await showProcessing()
  try { run.value = await api.service('listing-optimization', 'runs', { method: 'POST', body: JSON.stringify({ source_text: text }) }); localStorage.setItem('optimization-run', run.value.run_id); await loadRuns(); await watch(run.value.run_id) }
  catch (cause) { failProcessing(cause) }
}
async function reply() { const text = input.value.trim(); if (!text || processing.value) return; input.value = ''; pendingMessage.value = text; await showProcessing('已收到补充信息，Agent 正在继续处理'); try { run.value = await api.service('listing-optimization', `runs/${run.value.run_id}/reply`, { method: 'POST', body: JSON.stringify({ text }) }); pendingMessage.value = ''; await watch(run.value.run_id, -1) } catch (cause) { pendingMessage.value = ''; failProcessing(cause) } }
async function chatReply() { const text = input.value.trim(); if (!text || processing.value) return; input.value = ''; pendingMessage.value = text; await showProcessing('已收到消息，Agent 正在响应'); try { run.value = await api.service('listing-optimization', `runs/${run.value.run_id}/messages`, { method: 'POST', body: JSON.stringify({ text }) }); pendingMessage.value = ''; await watch(run.value.run_id, -1) } catch (cause) { pendingMessage.value = ''; failProcessing(cause) } }
async function action(type: 'approve' | 'retry') { if (processing.value) return; await showProcessing(type === 'approve' ? '已确认，Agent 正在生成上传稿' : 'Agent 正在重新处理'); try { run.value = await api.service('listing-optimization', `runs/${run.value.run_id}/actions`, { method: 'POST', body: JSON.stringify({ action: type }) }); await watch(run.value.run_id, -1) } catch (cause) { failProcessing(cause) } }
function reset() { localStorage.removeItem('optimization-run'); run.value = undefined; source.value = ''; input.value = ''; pendingMessage.value = ''; rounds.value = []; progress.value = '' }
async function renameRun(id: string, title: string) { const renamed = await api.service<any>('listing-optimization', `runs/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }); if (run.value?.run_id === id) run.value = renamed; await loadRuns() }
async function deleteRun(id: string) { await api.service('listing-optimization', `runs/${id}`, { method: 'DELETE' }); if (run.value?.run_id === id) reset(); await loadRuns() }
async function copyResult() { if (result.value?.rendered_text) await window.navigator.clipboard.writeText(result.value.rendered_text) }
onMounted(async () => { await loadRuns(); const remembered = localStorage.getItem('optimization-run'); const target = runs.value.find(item => item.run_id === remembered)?.run_id || runs.value[0]?.run_id; if (target) { try { await loadRun(target) } catch { localStorage.removeItem('optimization-run') } } })
</script>

<template>
  <section class="page workspace optimization-layout" :class="{ 'history-open': historyOpen }">
    <ConversationHistoryDrawer v-model:open="historyOpen" title="Listing 优化" :items="historyItems" :selected-id="run?.run_id" :busy="processing" @create="reset" @select="loadRun" @rename="renameRun" @delete="deleteRun"/>
    <main class="chat-shell glass-panel"><header class="workspace-head"><div><p class="eyebrow">DIAGNOSE FIRST, THEN OPTIMIZE</p><h1>文案诊断与安全改写</h1><p>粘贴完整 Listing，先诊断、确认，再生成可复制上传稿</p></div></header>
      <div ref="chat" class="chat optimizer-chat"><div v-if="!source" class="message assistant"><span class="avatar">AI</span><div class="bubble">发送完整 Listing，我会先进行市场研究与规则诊断</div></div><div v-if="source" class="message user"><span class="avatar">你</span><pre class="bubble">{{ source }}</pre></div><OptimizationWorkflowMessage v-for="(message, index) in run?.workflow_messages || []" :key="`workflow-${index}`" :message="message"/><template v-if="!run?.workflow_messages?.length"><OptimizationWorkflowMessage v-if="status === 'completed' && result?.diagnosis_report" :message="{ role: 'assistant', status: 'awaiting_approval', result }"/><div v-for="(replyText, index) in run?.replies || []" :key="`legacy-reply-${index}`" class="message user"><span class="avatar">你</span><div class="bubble">{{ replyText }}</div></div></template>
        <template v-if="status === 'completed'"><div class="message assistant"><span class="avatar">AI</span><div class="bubble">终稿已在右侧栏生成，可直接查看或复制。</div></div><div v-for="(message, index) in run?.chat_messages || []" :key="`chat-${index}`" class="message" :class="message.role"><span class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</span><div class="bubble">{{ message.content }}</div></div></template>
        <div v-if="result && status !== 'completed'" class="message assistant"><span class="avatar">AI</span><div class="bubble result-card">
          <template v-if="status === 'needs_clarification'"><h3>需要确认产品事实</h3><div v-for="question in result.questions" :key="question.code" class="question"><b>{{ question.question_zh || question.prompt_zh || question.question || question.code }}</b><p>{{ question.evidence_needed || question.reason_zh || question.reason }}</p></div><p class="muted">请在下方一次回复需要确认的事实；无法确认时可按问题提示保留现有安全稿</p></template>
          <template v-else-if="status === 'awaiting_approval'"><span class="success-tag">Stage 1 诊断完成</span><p>请审阅完整诊断报告，确认后生成上传稿</p><DiagnosisReport :report="result.diagnosis_report"/><button class="btn primary approval-button" :disabled="processing" @click="action('approve')">确认并生成上传稿</button></template>
          <template v-else-if="status === 'failed'"><h3 class="danger-text">优化未完成</h3><p>{{ result.message }}</p><small>错误代码：{{ result.code }}</small><div v-if="result.quality_failures?.length" class="failure-reasons"><b>质量门禁未通过原因</b><ol><li v-for="reason in result.quality_failures" :key="reason">{{ reason }}</li></ol></div><textarea v-if="result.last_candidate_text" class="output" :value="result.last_candidate_text"/><button class="btn ghost" :disabled="processing" @click="action('retry')">重试</button></template>
        </div></div><div v-if="pendingMessage" class="message user"><span class="avatar">你</span><div class="bubble">{{ pendingMessage }}</div></div><div v-if="processing" class="message assistant"><span class="avatar">AI</span><div class="bubble"><div class="typing"><i/><i/><i/> {{ progress || 'Agent 正在处理' }}</div></div></div><div v-if="error" class="alert">{{ error }}</div></div>
      <form class="composer" @submit.prevent="status === 'needs_clarification' ? reply() : chatEnabled ? chatReply() : submit()"><textarea v-model="input" :placeholder="status === 'needs_clarification' ? '回复确认结果；无法确认可写“删除”' : chatEnabled ? '询问或描述你希望如何修改当前终稿' : '粘贴完整 Listing'" @keydown.enter.exact.prevent="status === 'needs_clarification' ? reply() : chatEnabled ? chatReply() : submit()"/><button class="send" :disabled="processing || !input.trim()">发送</button></form>
    </main>
    <aside class="runtime glass-panel"><p class="eyebrow">LIVE RUNTIME</p><h2>实时运行层级</h2><div class="progress"><span :style="{ width: `${Math.min(100, progressStep / progressTotal * 100)}%` }"/></div><p>{{ progress || '等待 Listing 输入' }}</p><div class="steps"><span v-for="step in ['解析 Listing','市场研究与关键词','产品路由与专项规则','事实证据与冲突检查','综合诊断','生成或重写','语法语义复核','本土化审核']" :key="step">{{ step }}</span></div><h3>编辑与发布检查</h3><div v-if="status === 'failed' && result?.quality_failures?.length" class="runtime-gate-summary">最终发布门禁：未通过</div><div v-if="!rounds.length" class="muted">生成阶段将显示审核轮次与未通过原因</div><article v-for="round in rounds" :key="round.attempt" class="round-detail" :class="{ passed: round.passed }"><header>第 {{ round.attempt }}/{{ round.total }} 轮 · {{ round.passed ? '轮次复核通过' : '轮次复核未通过' }}</header><ul v-if="round.reasons?.length"><li v-for="reason in round.reasons" :key="reason">{{ reason }}</li></ul><p v-else>{{ round.passed ? '本轮检查通过；最终状态以发布门禁结果为准' : '本轮未返回具体失败原因' }}</p></article><section v-if="status === 'completed' && result?.rendered_text" class="runtime-final"><header><div><p class="eyebrow">RELEASE READY</p><h3>当前合格终稿</h3></div><span class="success-tag">已通过</span></header><textarea class="output" :value="result.rendered_text" readonly/><button class="btn primary" @click="copyResult">复制上传稿</button></section></aside>
  </section>
</template>

<style scoped>
.runtime-final { margin-top: 22px; padding-top: 18px; box-shadow: inset 0 1px 0 var(--border); }
.runtime-final header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.runtime-final h3 { margin: 4px 0 0; }
.runtime-final .output { min-height: 320px; max-height: 48vh; resize: vertical; font-size: 12px; }
.runtime-final .btn { width: 100%; }
.runtime-gate-summary { margin: 10px 0; padding: 10px 12px; border-radius: 12px; background: hsl(0 0% 100% / .065); color: hsl(0 0% 100% / .76); box-shadow: inset 3px 0 0 hsl(0 0% 100% / .52); font-weight: 600; font-size: 12px; }
</style>
