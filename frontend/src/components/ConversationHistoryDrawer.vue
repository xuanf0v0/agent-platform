<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

export interface HistoryItem {
  id: string
  title: string
  status?: string
  updatedAt?: string
  deletable?: boolean
}

const props = defineProps<{ title: string; items: HistoryItem[]; selectedId?: string; busy?: boolean; asin?: string; showAsin?: boolean }>()
const open = defineModel<boolean>('open', { default: true })
const emit = defineEmits<{
  create: []
  select: [id: string]
  rename: [id: string, title: string]
  delete: [id: string]
  asin: [value: string]
}>()

const editingId = ref('')
const editingTitle = ref('')
let media: MediaQueryList | undefined

function setOpen(value: boolean) { open.value = value }
function beginRename(item: HistoryItem) { editingId.value = item.id; editingTitle.value = item.title }
function cancelRename() { editingId.value = ''; editingTitle.value = '' }
function commitRename(item: HistoryItem) {
  const title = editingTitle.value.trim()
  if (title && title !== item.title) emit('rename', item.id, title)
  cancelRename()
}
function requestDelete(item: HistoryItem) {
  if (props.busy || item.deletable === false) return
  if (window.confirm(`永久删除“${item.title}”及其全部对话和上下文？此操作不可恢复。`)) emit('delete', item.id)
}
function select(id: string) { emit('select', id); if (media?.matches === false) setOpen(false) }
function displayTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function statusLabel(value?: string) {
  return ({ queued: '排队中', running: '处理中', needs_clarification: '待确认', awaiting_approval: '待批准', completed: '已完成', failed: '失败' } as Record<string, string>)[value || ''] || value || ''
}

onMounted(() => { media = window.matchMedia('(min-width: 901px)'); setOpen(media.matches) })
onUnmounted(() => { media = undefined })
</script>

<template>
  <button v-if="!open" class="history-toggle glass-panel" aria-label="展开历史对话" @click="setOpen(true)">☰<span>历史</span></button>
  <div v-if="open" class="history-backdrop" @click="setOpen(false)"/>
  <aside class="history-drawer glass-panel" :class="{ open }">
    <header class="history-head"><div><p class="eyebrow">HISTORY</p><h2>{{ title }}</h2></div><div class="history-head-actions"><button class="icon-btn" aria-label="新建对话" @click="emit('create')">＋</button><button class="drawer-close" aria-label="收起历史对话" @click="setOpen(false)">‹</button></div></header>
    <div v-if="showAsin" class="history-asin"><label>产品 ASIN</label><input :value="asin" placeholder="例如 B0XXXXXXXX" maxlength="10" @change="emit('asin', ($event.target as HTMLInputElement).value)"/><small>可从首轮资料自动提取，也可手动修改</small></div>
    <p v-if="!items.length" class="history-empty">暂无历史对话</p>
    <div class="history-list">
      <article v-for="item in items" :key="item.id" class="history-item" :class="{ selected: selectedId === item.id }">
        <template v-if="editingId === item.id">
          <input v-model="editingTitle" maxlength="120" autofocus @keydown.enter.prevent="commitRename(item)" @keydown.esc.prevent="cancelRename" @blur="commitRename(item)"/>
        </template>
        <button v-else class="history-select" @click="select(item.id)"><b>{{ item.title }}</b><small><span v-if="item.status" class="history-status" :class="item.status">{{ statusLabel(item.status) }}</span>{{ displayTime(item.updatedAt) }}</small></button>
        <div v-if="editingId !== item.id" class="history-actions"><button title="重命名" @click="beginRename(item)">✎</button><button title="永久删除" :disabled="busy || item.deletable === false" @click="requestDelete(item)">×</button></div>
      </article>
    </div>
  </aside>
</template>

<style scoped>
.history-drawer{display:none;min-width:0;border-radius:20px;padding:18px;overflow:hidden;flex-direction:column}.history-drawer.open{display:flex}.history-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.history-head h2{font-size:17px;margin:3px 0}.history-head-actions{display:flex;gap:6px}.drawer-close,.history-actions button{border:0;background:transparent;color:#6f91a5;cursor:pointer}.drawer-close{font-size:28px}.history-list{overflow:auto}.history-empty{color:var(--muted);font-size:12px}.history-item{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;border-radius:10px;margin:4px 0;background:transparent}.history-item.selected{background:rgba(67,223,252,.09)}.history-select{min-width:0;border:0;background:transparent;color:#7898ac;text-align:left;padding:10px;cursor:pointer}.selected .history-select{color:white}.history-select b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.history-select small{display:flex;align-items:center;gap:7px;color:#4f7185;font:9px monospace;margin-top:5px}.history-status{color:#7f9caf}.history-status.completed{color:#63e6b5}.history-status.failed{color:#ff8498}.history-status.running{color:var(--cyan)}.history-actions{display:flex;opacity:0;transition:.2s}.history-item:hover .history-actions,.history-item:focus-within .history-actions{opacity:1}.history-actions button{padding:5px}.history-actions button:last-child{color:#ff8498}.history-actions button:disabled{opacity:.35;cursor:not-allowed}.history-item input{min-width:0;margin:6px;padding:8px;background:#061522;border:1px solid rgba(67,223,252,.45);border-radius:7px;color:white}.history-toggle{border:0;border-radius:14px;color:var(--cyan);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;font-size:17px}.history-toggle span{font-size:9px;writing-mode:vertical-rl;letter-spacing:.15em}.history-backdrop{display:none}
.history-asin{display:grid;gap:5px;padding:12px 0;border-bottom:1px solid var(--border);margin-bottom:8px}.history-asin label{font-size:11px;color:#b9d5e5}.history-asin input{margin:0;min-width:0;padding:9px;background:#061522;border:1px solid var(--border);border-radius:7px;color:white;text-transform:uppercase}.history-asin small{font-size:9px;color:#557487}
@media(max-width:900px){.history-toggle{position:fixed;left:10px;top:90px;width:42px;height:42px;z-index:19}.history-toggle span{display:none}.history-drawer.open{position:fixed;left:10px;top:88px;bottom:10px;width:min(310px,calc(100vw - 35px));z-index:21}.history-backdrop{display:block;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:20}}
</style>
