<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ report: any }>()
const sourceLabel = computed(() => props.report?.scoring_source === 'llm' ? 'LLM 编辑评分' : '规则评分')
const p0 = computed(() => (props.report?.issues || []).filter((item: any) => item.level === 'P0'))
const p1 = computed(() => (props.report?.issues || []).filter((item: any) => item.level === 'P1'))
</script>

<template>
  <section v-if="report" class="diagnosis-report">
    <header class="diagnosis-title"><div><p class="eyebrow">SOURCE LISTING AUDIT</p><h2>源稿诊断报告</h2></div><div class="score-chip"><span>{{ sourceLabel }}</span><b>{{ report.average_score }}/10</b></div></header>
    <p class="diagnosis-disclaimer">{{ report.disclaimer_zh }}</p>
    <section class="report-section"><h3><span>1</span>字段检查</h3><div class="report-table-wrap"><table class="report-table"><thead><tr><th>字段</th><th>检查结果</th><th>状态</th><th>说明</th></tr></thead><tbody><tr v-for="row in report.field_checks" :key="`${row.field}-${row.metric}`"><td>{{ row.field }}</td><td>{{ row.metric }}</td><td><span class="audit-status" :class="row.status.toLowerCase()">{{ row.status }}</span></td><td>{{ row.note_zh }}</td></tr></tbody></table></div></section>
    <section class="report-section"><h3><span>2</span>主要问题</h3><details v-if="p0.length" class="issue-group critical" open><summary>P0 · 必须先修复 · {{ p0.length }}项</summary><article v-for="(issue, index) in p0" :key="`${issue.title}-${index}`"><b>{{ Number(index) + 1 }}. {{ issue.title }}</b><p>{{ issue.detail_zh }}</p></article></details><details v-if="p1.length" class="issue-group"><summary>P1 · 影响搜索与转化 · {{ p1.length }}项</summary><article v-for="(issue, index) in p1" :key="`${issue.title}-${index}`"><b>{{ Number(index) + 1 }}. {{ issue.title }}</b><p>{{ issue.detail_zh }}</p></article></details><p v-if="!p0.length && !p1.length" class="muted">未定位优先问题</p></section>
    <section v-if="report.backend" class="report-section"><h3><span>3</span>Backend Search Terms 诊断</h3><p>{{ report.backend.summary_zh }}</p><pre v-if="report.backend.terms" class="backend-terms">{{ report.backend.terms }}</pre><div class="backend-metrics"><b>{{ report.backend.bytes_used }}/{{ report.backend.max_bytes }}</b> UTF-8 bytes · <b>{{ report.backend.token_count }}</b> tokens · 可见字段重复约 <b>{{ Math.round(report.backend.duplication_pct) }}%</b></div><p v-if="report.backend.repeated_roots?.length"><b>与可见字段重复词根：</b>{{ report.backend.repeated_roots.join('、') }}</p><p v-if="report.backend.incremental_roots?.length"><b>增量词根：</b>{{ report.backend.incremental_roots.join('、') }}</p><p v-if="report.backend.uncovered_candidates?.length"><b>相关性候选（非验证高流量）：</b>{{ report.backend.uncovered_candidates.join('、') }}</p><p v-for="note in report.backend.risk_notes_zh" :key="note" class="risk-note">风险：{{ note }}</p></section>
    <section class="report-section"><h3><span>4</span>十维评分</h3><div class="score-grid"><article v-for="score in report.scores" :key="score.dimension"><div><b>{{ score.label_zh }}</b><strong>{{ score.score }}</strong></div><p>{{ score.rationale_zh }}</p></article></div><p class="average-score">平均分：<b>{{ report.average_score }}/10</b></p></section>
    <section class="report-section fix-order"><h3><span>5</span>建议处理顺序</h3><ol><li v-for="step in report.fix_order" :key="step">{{ step }}</li></ol></section>
  </section>
</template>
