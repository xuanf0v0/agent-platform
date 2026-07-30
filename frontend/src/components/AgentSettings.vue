<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ConfigField } from '../types'

const props = defineProps<{ agentId: string; running: boolean }>()
const fields = ref<ConfigField[]>([]); const edits = ref<Record<string, string>>({}); const logs = ref<string[]>([])
const tab = ref<'config' | 'logs'>('config'); const notice = ref('')
onMounted(async () => { fields.value = await api.getConfig(props.agentId) })
async function save() { fields.value = await api.updateConfig(props.agentId, edits.value); edits.value = {}; notice.value = '配置已保存' }
async function loadLogs() { tab.value = 'logs'; logs.value = (await api.getLogs(props.agentId)).lines }
</script>

<template>
  <div class="settings-panel">
    <div class="tabs"><button :class="{ active: tab === 'config' }" @click="tab = 'config'">配置</button><button :class="{ active: tab === 'logs' }" @click="loadLogs">运行日志</button></div>
    <div v-if="tab === 'config'" class="config-list">
      <label v-for="field in fields" :key="field.key">
        <span>{{ field.label }}</span>
        <select v-if="field.type === 'select'" :value="edits[field.key] ?? field.value" @change="edits[field.key] = ($event.target as HTMLSelectElement).value"><option v-for="option in field.options" :key="option">{{ option }}</option></select>
        <input v-else-if="field.type === 'boolean'" type="checkbox" :checked="(edits[field.key] ?? field.value).toLowerCase() === 'true'" @change="edits[field.key] = ($event.target as HTMLInputElement).checked ? 'true' : 'false'" />
        <input v-else :type="field.type === 'secret' ? 'password' : field.type === 'number' ? 'number' : 'text'" :value="edits[field.key] ?? field.value" :placeholder="field.is_masked ? '已设置，输入新值可修改' : ''" @input="edits[field.key] = ($event.target as HTMLInputElement).value" />
      </label>
      <div class="row end"><small>{{ notice }}</small><button class="btn primary" :disabled="!Object.keys(edits).length" @click="save">保存配置</button></div>
    </div>
    <pre v-else class="logs">{{ logs.length ? logs.join('\n') : running ? '暂无日志' : 'Agent 尚未启动' }}</pre>
  </div>
</template>
