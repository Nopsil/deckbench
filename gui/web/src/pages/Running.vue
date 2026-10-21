<template>
  <div class="page">
    <template v-if="!id">
      <div class="panel empty">
        <div class="big">{{ t('run.none') }}</div>
        <div>{{ t('run.noneHint') }}</div>
        <n-button type="primary" style="margin-top:18px" @click="$router.push('/new')">{{ t('nav.new') }}</n-button>
      </div>
      <div v-if="store.runs.length" class="panel">
        <h3>{{ t('run.recent') }}</h3>
        <div v-for="r in store.runs.slice(0, 6)" :key="r.id" class="recent" @click="$router.push('/run/' + r.id)">
          <n-tag size="small" :type="STATUS[r.status]?.type" :bordered="false">{{ STATUS[r.status]?.text || r.status }}</n-tag>
          <span class="rt">{{ runTitle(r) }}</span><span class="faint">{{ fmt.time(r.created) }}</span>
        </div>
      </div>
    </template>
    <template v-else-if="meta">
      <div class="panel head">
        <div class="row between">
          <div>
            <div class="row"><n-tag :type="STATUS[status]?.type" :bordered="false" round>
              <template #icon><span v-if="status === 'running'" class="pulse"></span></template>{{ STATUS[status]?.text || status }}</n-tag>
              <span class="faint mono" style="font-size:12px">{{ meta.id }}</span></div>
            <div class="ht">{{ runTitle(meta) }}</div>
            <div class="row" style="flex-wrap:wrap;gap:6px"><span v-for="t in paramChips" :key="t" class="chip">{{ t }}</span></div>
          </div>
          <div class="row">
            <n-popconfirm v-if="status === 'running'" :positive-text="t('common.ok')" :negative-text="t('common.cancel')" @positive-click="cancel">
              <template #trigger><n-button secondary type="error"><template #icon><n-icon :component="PlayerStop" /></template>{{ t('run.cancel') }}</n-button></template>
              {{ t('run.cancelQ') }}
            </n-popconfirm>
            <template v-else>
              <n-button secondary @click="rerun"><template #icon><n-icon :component="Refresh" /></template>{{ t('common.rerun') }}</n-button>
              <n-button v-if="status === 'done'" type="primary" @click="$router.push('/report/' + id)"><template #icon><n-icon :component="ChartBar" /></template>{{ t('run.viewReport') }}</n-button>
            </template>
          </div>
        </div>
        <div class="prog">
          <div class="track"><div class="fill" :class="status" :style="{ width: pct * 100 + '%' }"><div v-if="status === 'running'" class="shine"></div></div></div>
          <div class="pv">{{ Math.floor(pct * 100) }}%</div>
        </div>
        <div class="grid g4" style="margin-top:18px">
          <stat :label="meta.kind === 'batch' ? t('run.doneRuns') : t('run.doneFights')" :value="`${prog.done} / ${prog.total || '—'}`" />
          <stat :label="t('common.elapsed')" :value="fmt.secs(elapsed)" />
          <stat :label="t('run.speed')" :value="speed ? (meta.kind === 'batch' ? t('run.runsPerSec', { n: speed.toFixed(2) }) : t('run.fightsPerSec', { n: speed.toFixed(2) })) : '—'" />
          <stat :label="t('run.eta')" :value="status === 'running' ? (eta !== null ? fmt.secs(eta) : t('run.estimating')) : '—'" :hl="status === 'running'" />
        </div>
      </div>
      <div class="panel">
        <div class="row between" style="margin-bottom:10px"><h3 style="margin:0">{{ t('run.log') }}</h3>
          <n-checkbox v-model:checked="follow" size="small"><span class="muted" style="font-size:12.5px">{{ t('run.autoScroll') }}</span></n-checkbox></div>
        <div ref="logEl" class="log mono">
          <div v-for="(l, i) in lines" :key="i" :class="lineCls(l)">{{ l }}</div>
          <div v-if="!lines.length" class="faint">{{ t('run.waiting') }}</div>
        </div>
        <div v-if="status === 'failed'" class="hint" style="color:#E06C6C">{{ t('run.failedHint') }}</div>
      </div>
    </template>
    <div v-else class="panel empty"><n-spin /></div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NCheckbox, NIcon, NPopconfirm, NSpin, NTag, useMessage } from 'naive-ui'
import { PlayerStop, Refresh, ChartBar } from '@vicons/tabler'
import Stat from '../components/Stat.vue'
import { api, store, fmt, runTitle, STATUS } from '../api'
import { t, MESSAGES } from '../i18n'

const route = useRoute()
const router = useRouter()
const msg = useMessage()
const id = computed(() => route.params.id)
const meta = ref(null)
const lines = ref([])
const status = ref('running')
const prog = ref({ done: 0, total: 0 })
const follow = ref(true)
const logEl = ref(null)
const now = ref(Date.now() / 1000)
let es = null
let tick = null
let firstProg = null

const pct = computed(() => (prog.value.total ? prog.value.done / prog.value.total : status.value === 'done' ? 1 : 0))
const elapsed = computed(() => {
  if (!meta.value) return null
  if (meta.value.secs && status.value !== 'running') return meta.value.secs
  return now.value - meta.value.started_ts
})
const speed = computed(() => (elapsed.value > 0 && prog.value.done ? prog.value.done / elapsed.value : null))
const eta = computed(() => {
  if (!speed.value || !prog.value.total || prog.value.done < 2) return null
  return (prog.value.total - prog.value.done) / speed.value
})
const paramChips = computed(() => {
  const p = meta.value?.params || {}
  if (meta.value?.kind === 'batch') {
    const x = [t('kind.batch'), store.charName(p.char), 'A' + p.asc, t('chip.nRuns', { n: p.n }), store.agentName('batch', p.agent), t('chip.parallel', { n: p.procs })]
    if (p.variants?.length) x.push(t('chip.variant', { v: p.variants.join('+') }))
    return x
  }
  return [t('kind.combat'), p.preset ? t('chip.preset', { id: p.preset }) : t('nt.nDecks', { n: (p.decks || []).length }), t('chip.perCell', { n: p.fights }), store.agentName('combat', p.agent), t('chip.seed', { s: p.seed })]
})
// 日志行按所有语言的「胜利/完成」「出错/失败」词着色（日志是开始运行时的语言，界面语言之后可能换过）
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const words = (keys) => new RegExp(Object.values(MESSAGES).flatMap((m) => keys.map((k) => m[k]).filter(Boolean)).map(esc).join('|') || '$^')
const OK_RE = words(['log.win', 'log.doneWord'])
const BAD_RE = words(['log.error', 'log.failWord'])
function lineCls(l) {
  if (OK_RE.test(l)) return 'ok'
  if (/Error|Traceback/.test(l) || BAD_RE.test(l)) return 'bad'
  if (/^\[/.test(l)) return ''
  return 'info'
}
function scroll() { if (follow.value) nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight }) }

async function connect() {
  close()
  lines.value = []
  if (!id.value) {
    await store.loadRuns()
    const r = store.runs.find((x) => x.status === 'running')
    if (r) router.replace('/run/' + r.id)
    return
  }
  try { meta.value = await api.get('/api/runs/' + id.value) } catch (e) { msg.error(e.message); return }
  status.value = meta.value.status
  prog.value = meta.value.progress || { done: 0, total: 0 }
  es = new EventSource(`/api/runs/${id.value}/stream?since=0`)
  es.onmessage = (ev) => {
    const d = JSON.parse(ev.data)
    if (d.lines?.length) { lines.value.push(...d.lines); if (lines.value.length > 4000) lines.value.splice(0, lines.value.length - 4000); scroll() }
    if (d.progress) prog.value = d.progress
    if (d.status) status.value = d.status
    if (d.final) {
      meta.value = d.meta
      close()
      store.loadRuns()
      if (d.status === 'done') msg.success(t('run.finished'))
    }
  }
  es.onerror = () => { /* 浏览器会自动重连 */ }
}
function close() { if (es) { es.close(); es = null } }
async function cancel() { try { await api.post(`/api/runs/${id.value}/cancel`); msg.info(t('run.cancelSent')) } catch (e) { msg.error(e.message) } }
async function rerun() { try { const m = await api.post(`/api/runs/${id.value}/rerun`); store.loadRuns(); router.push('/run/' + m.id) } catch (e) { msg.error(e.message) } }
watch(id, connect)
onMounted(() => { connect(); tick = setInterval(() => (now.value = Date.now() / 1000), 1000) })
onUnmounted(() => { close(); clearInterval(tick) })
</script>

<style scoped>
.head .ht { font-size: 20px; font-weight: 700; margin: 10px 0 10px; }
.prog { display: flex; align-items: center; gap: 16px; margin-top: 22px; }
.track { flex: 1; height: 12px; border-radius: 99px; background: #26262B; overflow: hidden; }
.fill { position: relative; height: 100%; border-radius: 99px; background: linear-gradient(90deg, #C4664A, #E8946F); transition: width .5s ease; overflow: hidden; }
.fill.done { background: linear-gradient(90deg, #6FA36B, #8FBF8F); }
.fill.failed, .fill.cancelled, .fill.interrupted { background: #5A5A62; }
.shine { position: absolute; inset: 0; background: linear-gradient(90deg, transparent, rgba(255,255,255,.25), transparent); animation: sh 1.6s infinite; }
@keyframes sh { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
.pv { font-size: 22px; font-weight: 700; width: 64px; text-align: right; color: #F0A486; }
.pulse { width: 8px; height: 8px; border-radius: 50%; background: #E3B47E; animation: pu 1.2s infinite; display: inline-block; }
@keyframes pu { 50% { opacity: .3; } }
.log { height: 380px; overflow-y: auto; background: #111113; border: 1px solid #26262B; border-radius: 10px; padding: 12px 14px; font-size: 12.5px; line-height: 1.7; color: #B9B4AC; white-space: pre-wrap; word-break: break-all; }
.log .ok { color: #9FCC9F; }
.log .bad { color: #E88080; }
.log .info { color: #E3B47E; }
.recent { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 9px; cursor: pointer; }
.recent:hover { background: #24242A; }
.rt { flex: 1; font-weight: 500; }
</style>
