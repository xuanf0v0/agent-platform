<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, readSse } from '../api/client'
import DiagnosisReport from '../components/DiagnosisReport.vue'

const source = ref(''); const run = ref<any>(); const input = ref(''); const processing = ref(false); const progress = ref(''); const progressStep = ref(0); const progressTotal = ref(8); const rounds = ref<any[]>([]); const error = ref('')
const result = computed(() => run.value?.result); const status = computed(() => run.value?.status || 'idle')
async function watch(runId: string, after = -1) {
  processing.value = true; error.value = ''
  try {
    const response = await fetch(`${api.serviceUrl('listing-optimization', `runs/${runId}/events`)}?after=${after}`)
    await readSse(response, (event, data) => {
      if (event === 'progress' || event === 'status') { progress.value = data.content; progressStep.value = data.step ?? progressStep.value; progressTotal.value = data.total ?? progressTotal.value }
      if (event === 'quality') rounds.value = [...rounds.value.filter(item => item.attempt !== data.attempt), data].sort((a, b) => a.attempt - b.attempt)
      if (event === 'result') run.value = { ...run.value, status: data.status, result: data.result }
    })
    run.value = await api.service('listing-optimization', `runs/${runId}`); localStorage.setItem('optimization-run', runId)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { processing.value = false }
}
async function submit() {
  const text = input.value.trim(); if (!text || processing.value) return
  source.value = text; input.value = ''; rounds.value = []; progress.value = '已接收 Listing，开始处理…'
  run.value = await api.service('listing-optimization', 'runs', { method: 'POST', body: JSON.stringify({ source_text: text }) }); await watch(run.value.run_id)
}
async function reply() { const text = input.value.trim(); if (!text) return; input.value = ''; run.value = await api.service('listing-optimization', `runs/${run.value.run_id}/reply`, { method: 'POST', body: JSON.stringify({ text }) }); await watch(run.value.run_id, -1) }
async function action(type: 'approve' | 'retry') { run.value = await api.service('listing-optimization', `runs/${run.value.run_id}/actions`, { method: 'POST', body: JSON.stringify({ action: type }) }); await watch(run.value.run_id, -1) }
function reset() { localStorage.removeItem('optimization-run'); run.value = undefined; source.value = ''; input.value = ''; rounds.value = []; progress.value = '' }
async function copyResult() { if (result.value?.rendered_text) await window.navigator.clipboard.writeText(result.value.rendered_text) }
onMounted(async () => { const id = localStorage.getItem('optimization-run'); if (!id) return; try { run.value = await api.service('listing-optimization', `runs/${id}`); source.value = run.value.source_text; if (run.value.status === 'running' || run.value.status === 'queued') await watch(id) } catch { localStorage.removeItem('optimization-run') } })
</script>

<template>
  <section class="page workspace optimization-layout">
    <main class="chat-shell glass-panel"><header class="workspace-head"><div><p class="eyebrow">DIAGNOSE FIRST, THEN OPTIMIZE</p><h1>文案诊断与安全改写</h1><p>粘贴完整 Listing，先诊断、确认，再生成可复制上传稿</p></div><button v-if="run" class="btn ghost" @click="reset">新建对话</button></header>
      <div class="chat optimizer-chat"><div v-if="!source" class="message assistant"><span class="avatar">AI</span><div class="bubble">发送完整 Listing，我会先进行市场研究与规则诊断</div></div><div v-if="source" class="message user"><span class="avatar">你</span><pre class="bubble">{{ source }}</pre></div><div v-for="(replyText, index) in run?.replies || []" :key="index" class="message user"><span class="avatar">你</span><div class="bubble">{{ replyText }}</div></div>
        <div v-if="processing" class="message assistant"><span class="avatar">AI</span><div class="bubble"><div class="typing"><i/><i/><i/> {{ progress || 'Agent 正在处理' }}</div></div></div>
        <div v-if="result" class="message assistant"><span class="avatar">AI</span><div class="bubble result-card">
          <template v-if="status === 'needs_clarification'"><h3>需要确认产品事实</h3><div v-for="question in result.questions" :key="question.code" class="question"><b>{{ question.prompt_zh || question.question || question.code }}</b><p>{{ question.reason_zh || question.reason }}</p></div><p class="muted">请在下方一次回复需要确认或删除的事实</p></template>
          <template v-else-if="status === 'awaiting_approval'"><span class="success-tag">Stage 1 诊断完成</span><p>请审阅完整诊断报告，确认后生成上传稿</p><DiagnosisReport :report="result.diagnosis_report"/><button class="btn primary approval-button" @click="action('approve')">确认并生成上传稿</button></template>
          <template v-else-if="status === 'completed'"><span class="success-tag">发布门禁通过</span><h3>优化后 Listing</h3><textarea class="output" :value="result.rendered_text"/><button class="btn primary" @click="copyResult">复制上传稿</button></template>
          <template v-else-if="status === 'failed'"><h3 class="danger-text">优化未完成</h3><p>{{ result.message }}</p><small>错误代码：{{ result.code }}</small><textarea v-if="result.last_candidate_text" class="output" :value="result.last_candidate_text"/><button class="btn ghost" @click="action('retry')">重试</button></template>
        </div></div><div v-if="error" class="alert">{{ error }}</div></div>
      <form class="composer" @submit.prevent="status === 'needs_clarification' ? reply() : submit()"><textarea v-model="input" :placeholder="status === 'needs_clarification' ? '回复确认结果；无法确认可写“删除”' : '粘贴完整 Listing'" @keydown.enter.exact.prevent="status === 'needs_clarification' ? reply() : submit()"/><button class="send" :disabled="processing || !input.trim()">发送</button></form>
    </main>
    <aside class="runtime glass-panel"><p class="eyebrow">LIVE RUNTIME</p><h2>实时运行层级</h2><div class="progress"><span :style="{ width: `${Math.min(100, progressStep / progressTotal * 100)}%` }"/></div><p>{{ progress || '等待 Listing 输入' }}</p><div class="steps"><span v-for="step in ['解析 Listing','市场研究与关键词','产品路由与专项规则','事实证据与冲突检查','综合诊断','生成或重写','语法语义复核','本土化审核']" :key="step">{{ step }}</span></div><h3>质量门禁</h3><div v-if="!rounds.length" class="muted">生成阶段将显示审核轮次</div><div v-for="round in rounds" :key="round.attempt" class="round" :class="{ passed: round.passed }">第 {{ round.attempt }}/{{ round.total }} 轮 · {{ round.passed ? '通过' : '重写' }}</div></aside>
  </section>
</template>
