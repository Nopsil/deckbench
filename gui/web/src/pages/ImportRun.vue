<template>
  <div class="page">
    <div class="panel">
      <div class="label">{{ t('imp.path') }}</div>
      <div class="row">
        <n-input v-model:value="path" :placeholder="t('imp.pathPh')" style="flex:1" @keyup.enter="loadPath" />
        <n-button type="primary" :loading="loading" @click="loadPath">{{ t('imp.load') }}</n-button>
        <n-upload :custom-request="upload" :show-file-list="false">
          <n-button secondary :loading="loading">{{ t('imp.upload') }}</n-button>
        </n-upload>
        <n-button secondary :loading="finding" @click="find">{{ t('imp.discover') }}</n-button>
      </div>
      <div v-if="discoverError" class="hint warn">{{ discoverError }}</div>
      <div v-if="roots.length" class="roots">
        <button v-for="r in roots" :key="r.path" class="root" @click="path = r.path; loadPath()">
          <span class="mono">{{ r.path }}</span>
          <span class="faint">{{ t('imp.discoverFound', { n: r.history }) }}</span>
        </button>
      </div>
      <div v-else-if="foundOnce && !roots.length" class="hint">{{ t('imp.discoverEmpty') }}</div>
    </div>

    <div v-if="error" class="panel state">
      <div class="big">{{ t('imp.errTitle') }}</div>
      <div class="detail">{{ error }}</div>
      <div class="hint">{{ t('imp.errHint') }}</div>
    </div>
    <div v-else-if="loading" class="panel state"><n-spin /><div class="hint">{{ t('imp.loading') }}</div></div>

    <template v-else-if="doc && doc.kind === 'folder'">
      <div class="panel">
        <h3>{{ t('imp.folder') }}</h3>
        <div class="hint mono">{{ doc.path }}</div>
        <div v-if="(doc.warnings || []).length" class="warn-block">
          <div class="label">{{ t('imp.warnings') }}</div>
          <div v-for="w in doc.warnings || []" :key="w.code" class="hint warn">{{ warnText(w) }}</div>
        </div>
        <div v-if="badCount && !okCount" class="hint warn">{{ t('imp.allUnreadable') }}</div>
        <div v-else-if="badCount" class="hint warn">{{ t('imp.someUnreadable', { bad: badCount, ok: okCount }) }}</div>
        <div v-else class="hint">{{ t('imp.pickRun') }}</div>
        <table class="runs">
          <thead>
            <tr>
              <th>{{ t('imp.file') }}</th>
              <th>{{ t('imp.seed') }}</th>
              <th>{{ t('imp.character') }}</th>
              <th>{{ t('imp.ascension') }}</th>
              <th>{{ t('imp.result') }}</th>
              <th>{{ t('imp.floor') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in doc.entries" :key="e.path" :class="{ on: selected === e, bad: !e.run }" @click="pick(e)">
              <td class="mono">{{ e.file }}</td>
              <template v-if="e.run">
                <td class="mono">{{ e.run.seed || t('common.none') }}</td>
                <td>{{ who(e.run) }}</td>
                <td>A{{ e.run.ascension }}</td>
                <td>{{ t('imp.result.' + e.run.result) }}</td>
                <td>{{ (e.run.route || []).length }}</td>
              </template>
              <template v-else>
                <td colspan="5" class="bad-cell">
                  <b>{{ t('imp.unreadable') }}</b>
                  <div class="hint warn">{{ errText(e.error) }}</div>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <run-detail v-if="!error && !loading && run" :run="run" />
    <div v-else-if="!error && !loading && !(doc && doc.kind === 'folder')" class="panel state">
      <div class="big">{{ t('imp.emptyTitle') }}</div>
      <div class="detail">{{ t('imp.emptyHint') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NInput, NSpin, NUpload, useMessage } from 'naive-ui'
import { api } from '../api'
import { t, has } from '../i18n'
import RunDetail from '../components/RunDetail.vue'

const route = useRoute()

const msg = useMessage()
const path = ref('')
const loading = ref(false)
const finding = ref(false)
const foundOnce = ref(false)
const roots = ref([])
const doc = ref(null)
const error = ref('')
const discoverError = ref('')
const selected = ref(null)

const run = computed(() => {
  if (!doc.value) return null
  if (doc.value.kind === 'run') return doc.value.run
  return selected.value && selected.value.run
})
const badCount = computed(() => ((doc.value && doc.value.entries) || []).filter((e) => !e.run).length)
const okCount = computed(() => ((doc.value && doc.value.entries) || []).filter((e) => e.run).length)

function qstr(v) {
  if (Array.isArray(v)) v = v[0]
  return typeof v === 'string' ? v : ''
}
function warnText(w) {
  const k = 'imp.warn.' + (w.code || '')
  return has(k) ? t(k, w) : (w.code || '')
}
function errText(err) {
  if (!err) return t('imp.unreadable')
  const k = 'imp.err.' + (err.code || '')
  const base = has(k) ? t(k, err) : (err.code || t('imp.unreadable'))
  const detail = err.detail == null ? '' : String(err.detail).trim()
  if (!detail || base.includes(detail)) return base
  const clip = detail.length > 160 ? detail.slice(0, 160) + '...' : detail
  return t('imp.err.withDetail', { text: base, detail: clip })
}
function who(r) {
  return (r.players || []).map((p) => p.character || t('common.none')).join(', ')
}
function pick(e) {
  if (e && e.run) selected.value = e
}
async function loadPath() {
  if (!path.value.trim()) {
    doc.value = null
    selected.value = null
    error.value = t('imp.needPath')
    return
  }
  loading.value = true
  error.value = ''
  selected.value = null
  try {
    doc.value = await api.post('/api/import', { path: path.value.trim() })
    if (doc.value.kind === 'folder') selected.value = (doc.value.entries || []).find((e) => e.run) || null
  } catch (e) { doc.value = null; error.value = e.message; msg.error(e.message) }
  finally { loading.value = false }
}
async function upload({ file, onFinish, onError }) {
  loading.value = true
  error.value = ''
  const fd = new FormData()
  fd.append('file', file.file)
  const name = (file && file.name) || ''
  try {
    doc.value = await api.upload('/api/import/upload', fd)
    selected.value = null
    onFinish()
  } catch (e) {
    doc.value = null
    selected.value = null
    error.value = name ? t('imp.err.fileNamed', { file: name, text: e.message }) : e.message
    msg.error(error.value)
    onError()
  } finally { loading.value = false }
}
async function find() {
  finding.value = true
  discoverError.value = ''
  try {
    const d = await api.get('/api/saves/discover')
    roots.value = d.roots || []
    foundOnce.value = true
  } catch (e) { discoverError.value = e.message; msg.error(e.message) }
  finally { finding.value = false }
}
function applyQueryPath() {
  const q = qstr(route.query.path).trim()
  if (q) {
    path.value = q
    loadPath()
  }
}
onMounted(applyQueryPath)
watch(() => route.query.path, (v, prev) => { if (qstr(v) && qstr(v) !== qstr(prev)) applyQueryPath() })
</script>

<style scoped>
.roots { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.root { text-align: left; background: #26262B; border: 1px solid #2E2E34; color: inherit; border-radius: 10px; padding: 8px 12px; cursor: pointer; display: flex; justify-content: space-between; gap: 12px; }
.root:hover { border-color: #D97757; }
.runs { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
.runs th { text-align: left; color: #9C978F; font-weight: 600; padding: 6px 8px; }
.runs td { padding: 8px; border-top: 1px solid #2A2A30; }
.runs tr.on td { background: rgba(217,119,87,.12); }
.runs tbody tr { cursor: pointer; }
.runs tbody tr.bad { cursor: default; }
.runs tr.bad td { background: rgba(224, 108, 108, .06); }
.bad-cell { color: #E0A86C; }
.state { text-align: center; }
.state .big { font-size: 15px; color: #B9B4AC; margin-bottom: 8px; }
.state .detail { color: #CFCAC2; font-size: 13.5px; line-height: 1.55; text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; }
.hint.warn { color: #E0A86C; }
.warn-block { margin-top: 10px; }
.page > .panel { margin-top: 16px; }
.page > .panel:first-child { margin-top: 0; }
</style>
