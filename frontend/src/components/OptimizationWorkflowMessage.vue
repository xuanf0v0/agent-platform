<script setup lang="ts">
import DiagnosisReport from './DiagnosisReport.vue'

defineProps<{ message: any }>()
</script>

<template>
  <div v-if="message.role === 'user'" class="message user">
    <span class="avatar">你</span><div class="bubble">{{ message.content }}</div>
  </div>
  <div v-else class="message assistant">
    <span class="avatar">AI</span>
    <div class="bubble result-card">
      <template v-if="message.status === 'needs_clarification'">
        <span class="history-tag">历史记录 · 事实确认</span><h3>需要确认产品事实</h3>
        <div v-for="question in message.result?.questions || []" :key="question.code" class="question">
          <b>{{ question.question_zh || question.prompt_zh || question.question || question.code }}</b>
          <p>{{ question.evidence_needed || question.reason_zh || question.reason }}</p>
        </div>
      </template>
      <template v-else-if="message.status === 'awaiting_approval'">
        <span class="history-tag">历史记录 · Listing 诊断</span>
        <DiagnosisReport v-if="message.result?.diagnosis_report" :report="message.result.diagnosis_report"/>
      </template>
      <template v-else-if="message.status === 'failed'">
        <span class="history-tag">历史记录 · 失败</span><h3 class="danger-text">优化未完成</h3>
        <p>{{ message.result?.message }}</p>
        <ol v-if="message.result?.quality_failures?.length"><li v-for="reason in message.result.quality_failures" :key="reason">{{ reason }}</li></ol>
      </template>
      <template v-else>
        <span class="history-tag">历史记录</span><p>{{ message.result?.message || `阶段状态：${message.status}` }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.history-tag { display: inline-block; margin-bottom: 10px; color: var(--muted); font: 10px monospace; }
</style>
