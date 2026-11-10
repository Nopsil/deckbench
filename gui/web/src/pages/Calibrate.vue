<template>
  <div class="page" data-page="calibrate">
    <div class="panel">
      <div class="label">{{ t('cal.real') }}</div>
      <div class="row">
        <n-input v-model:value="real" :placeholder="t('cal.realPh')" style="flex:1" @keyup.enter="compare" />
        <n-button secondary :loading="findingReals" @click="findReals">{{ t('cal.findReals') }}</n-button>
      </div>
      <div v-if="realError" class="hint warn">{{ realError }}</div>
      <div v-if="reals.length" class="roots">
        <div class="label">{{ t('cal.reals') }}</div>
        <button v-for="item in reals" :key="item.path" class="root" :class="{ on: item.path === real }" @click="pickReal(item.path)">
          <span class="mono">{{ item.path }}</span>
        </button>
        <div v-if="realsTruncated" class="hint">{{ t('cal.truncated', { n: reals.length }) }}</div>
      </div>
      <div v-else-if="foundReals && !reals.length" class="hint">{{ t('cal.realsEmpty') }}</div>

      <div class="label sim-label">{{ t('cal.sim') }}</div>
      <div class="row">
        <n-input :value="sim" :placeholder="t('cal.simPh')" style="flex:1" @update:value="typeSim" @keyup.enter="compare" />
        <n-upload :custom-request="stageUpload" :show-file-list="false">
          <n-button secondary>{{ t('cal.upload') }}</n-button>
        </n-upload>
        <n-button secondary :loading="findingSims" @click="findSims">{{ t('cal.findSims') }}</n-button>
        <n-button type="primary" :loading="loading" @click="compare">{{ t('cal.compare') }}</n-button>
      </div>
      <div v-if="uploadName" class="hint">{{ t('cal.uploadReady', { name: uploadName }) }}</div>
      <div class="hint">{{ t('cal.readOnly') }}</div>
      <div v-if="simError" class="hint warn">{{ simError }}</div>
      <div v-if="sims.length" class="roots">
        <div class="label">{{ t('cal.sims') }}</div>
        <button v-for="item in sims" :key="item.path" class="root" :class="{ on: item.path === sim && !uploadName }" @click="pickSim(item.path)">
          <span class="mono">{{ item.path }}</span>
        </button>
        <div v-if="simsTruncated" class="hint">{{ t('cal.truncated', { n: sims.length }) }}</div>
      </div>
      <div v-else-if="foundSims && !sims.length" class="hint">{{ t('cal.simsEmpty') }}</div>
    </div>

    <div v-if="error" class="panel state">
      <div class="big">{{ t('cal.errTitle') }}</div>
      <div class="detail">{{ error }}</div>
    </div>
    <div v-else-if="loading" class="panel state"><n-spin /><div class="hint">{{ t('cal.loading') }}</div></div>

    <template v-else-if="report">
      <div class="panel">
        <div class="between head">
          <div>
            <h3>{{ t('imp.seed') }} {{ report.seed || t('common.none') }}</h3>
            <div class="hint">{{ t('cal.summary', summary) }}</div>
          </div>
          <div class="hint">{{ report.character || t('common.none') }} · A{{ report.ascension }}</div>
        </div>
        <div v-if="deckText" class="hint">{{ t('cal.deck') }} <span class="mono">{{ deckText }}</span></div>
        <div v-if="excludedText" class="hint">{{ t('cal.excluded', { text: excludedText }) }}</div>
        <div class="hint mono paths">{{ report.real_path }}</div>
        <div v-if="report.sim_path" class="hint mono">{{ report.sim_path }}</div>
      </div>

      <div class="panel">
        <div class="table-wrap">
          <table class="fights">
            <thead>
              <tr>
                <th>{{ t('cal.floor') }}</th>
                <th>{{ t('cal.room') }}</th>
                <th>{{ t('cal.encounter') }}</th>
                <th>{{ t('cal.realHp') }}</th>
                <th>{{ t('cal.mean') }}</th>
                <th>{{ t('cal.p10') }}</th>
                <th>{{ t('cal.p90') }}</th>
                <th>{{ t('cal.percentile') }}</th>
                <th>{{ t('cal.gap') }}</th>
                <th>{{ t('cal.band') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in rows" :key="rowKey(f)"
                  :class="{ gap: f.likely_sim_gap, unmatched: f.status === 'unmatched', quiet: f.status === 'not_a_fight' }"
                  :data-status="f.status" :data-floor="f.floor" :data-gap="f.likely_sim_gap ? '1' : '0'">
                <td class="mono">{{ f.floor == null ? t('common.none') : f.floor }}</td>
                <td>{{ roomText(f.room) }}</td>
                <td class="mono enc">{{ f.encounter || t('common.none') }}</td>
                <td class="mono">{{ num(f.real_hp_lost) }}</td>
                <td class="mono">{{ num(f.mean) }}</td>
                <td class="mono">{{ num(f.p10) }}</td>
                <td class="mono">{{ num(f.p90) }}</td>
                <td class="mono">{{ num(f.percentile) }}</td>
                <td>
                  <span v-if="f.status === 'compared'" class="badge" :class="{ gap: f.likely_sim_gap }">
                    {{ f.likely_sim_gap ? t('cal.gapYes') : t('cal.gapNo') }}
                  </span>
                  <span v-else class="reason">{{ reasonText(f) }}</span>
                </td>
                <td>
                  <svg v-if="f.strip" class="strip" viewBox="0 0 120 18" role="img" :aria-label="stripLabel(f)">
                    <rect class="track" x="0" y="6" width="120" height="6" rx="3" />
                    <rect v-if="f.strip.whisker" class="whisker" :x="f.strip.whisker.x" y="7" :width="f.strip.whisker.width" height="4" rx="2" />
                    <rect v-if="f.strip.band" class="band" :x="f.strip.band.x" y="4.5" :width="f.strip.band.width" height="9" rx="2" />
                    <line v-if="f.strip.real != null" class="mark" :class="{ gap: f.likely_sim_gap }" :x1="f.strip.real" y1="1" :x2="f.strip.real" y2="17" />
                    <circle v-if="f.strip.real != null" class="mark" :class="{ gap: f.likely_sim_gap }" :cx="f.strip.real" cy="9" r="2.5" />
                  </svg>
                  <span v-else class="faint">{{ t('common.none') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="hint">{{ t('cal.legend') }}</div>
      </div>
    </template>

    <div v-else class="panel state">
      <div class="big">{{ t('cal.emptyTitle') }}</div>
      <div class="detail">{{ t('cal.emptyHint') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NInput, NSpin, NUpload, useMessage } from 'naive-ui'
import { api } from '../api'
import { t, has } from '../i18n'

const STRIP_W = 120
const route = useRoute()
const msg = useMessage()

function qstr(v) {
  if (Array.isArray(v)) v = v[0]
  return v == null ? '' : String(v)
}

const real = ref(qstr(route.query.real))
const sim = ref(qstr(route.query.sim))
const uploadName = ref('')
const staged = ref(null)
const reals = ref([])
const sims = ref([])
const realsTruncated = ref(false)
const simsTruncated = ref(false)
const foundReals = ref(false)
const foundSims = ref(false)
const realError = ref('')
const simError = ref('')
const error = ref('')
const report = ref(null)
const loading = ref(false)
const findingReals = ref(false)
const findingSims = ref(false)

const rows = computed(() => ((report.value && report.value.fights) || []).map((f, i) => ({
  ...f,
  _i: i,
  strip: makeStrip(f),
})))
const summary = computed(() => ({
  matched: report.value ? report.value.sim_matched : 0,
  rows: report.value ? report.value.sim_rows : 0,
  gaps: report.value && report.value.gaps ? report.value.gaps.length : 0,
  unmatched: report.value && report.value.unmatched ? report.value.unmatched.length : 0,
}))
const deckText = computed(() => {
  const path = (report.value && report.value.deck_path) || []
  return path.length ? path.join(t('sep.list')) : ''
})
const excludedText = computed(() => {
  const ex = (report.value && report.value.excluded) || {}
  const bits = Object.keys(ex).map((k) => {
    const label = reasonCode(k)
    return label + ' ' + ex[k]
  })
  return bits.join(t('sep.list'))
})

function rowKey(f) {
  return String(f.floor) + ':' + String(f._i)
}
function num(v) {
  if (v == null || v === '' || Number.isNaN(Number(v))) return t('common.none')
  const n = Number(v)
  if (!Number.isFinite(n)) return t('common.none')
  if (Number.isInteger(n)) return String(n)
  return String(Math.round(n * 100) / 100)
}
function roomText(room) {
  if (!room) return t('common.none')
  if (has('mp.' + room)) return t('mp.' + room)
  if (has('room.' + room)) return t('room.' + room)
  return String(room)
}
function reasonCode(code) {
  if (!code) return t('common.none')
  const k = 'cal.reason.' + code
  return has(k) ? t(k) : String(code)
}
function reasonText(f) {
  if (!f || f.status === 'compared') return ''
  if (f.status === 'not_a_fight') return t('cal.notAFight')
  return reasonCode(f.reason)
}
function axis(values) {
  const nums = values.map(Number).filter((n) => Number.isFinite(n))
  if (!nums.length) return null
  let lo = Math.min(0, ...nums)
  let hi = Math.max(...nums)
  if (hi <= lo) hi = lo + 1
  const pad = (hi - lo) * 0.08
  lo -= pad
  hi += pad
  return (v) => {
    const n = Number(v)
    if (!Number.isFinite(n)) return null
    const x = ((n - lo) / (hi - lo)) * STRIP_W
    return Math.min(STRIP_W, Math.max(0, x))
  }
}
function span(x, a, b) {
  const xa = x(a)
  const xb = x(b)
  if (xa == null || xb == null) return null
  const left = Math.min(xa, xb)
  const width = Math.min(STRIP_W - left, Math.max(Math.abs(xb - xa), 1.5))
  return { x: left, width }
}
function makeStrip(f) {
  if (!f || f.status !== 'compared') return null
  const x = axis([f.p5, f.p95, f.p10, f.p90, f.real_hp_lost])
  if (!x) return null
  return { whisker: span(x, f.p5, f.p95), band: span(x, f.p10, f.p90), real: x(f.real_hp_lost) }
}
function stripLabel(f) {
  return t('cal.bandLabel', { real: num(f.real_hp_lost), p10: num(f.p10), p90: num(f.p90) })
}

function clearUpload() {
  uploadName.value = ''
  staged.value = null
}
function typeSim(v) {
  sim.value = v == null ? '' : String(v)
  clearUpload()
}
function pickReal(path) {
  real.value = path
  if ((sim.value && sim.value.trim()) || staged.value) compare()
}
function pickSim(path) {
  clearUpload()
  sim.value = path
  if (real.value && real.value.trim()) compare()
}
function stageUpload({ file, onFinish, onError }) {
  const raw = file && file.file
  if (!raw) {
    if (onError) onError()
    return
  }
  staged.value = raw
  uploadName.value = (file && file.name) || raw.name || 'runs.jsonl'
  sim.value = ''
  if (onFinish) onFinish()
  if (real.value && real.value.trim()) compare()
}

async function findReals() {
  findingReals.value = true
  realError.value = ''
  try {
    const doc = await api.get('/api/calibrate/reals')
    reals.value = doc.runs || []
    realsTruncated.value = !!doc.truncated
    foundReals.value = true
  } catch (e) {
    realError.value = e.message
    msg.error(e.message)
  } finally {
    findingReals.value = false
  }
}
async function findSims() {
  findingSims.value = true
  simError.value = ''
  try {
    const doc = await api.get('/api/calibrate/sims')
    sims.value = doc.sims || []
    simsTruncated.value = !!doc.truncated
    foundSims.value = true
  } catch (e) {
    simError.value = e.message
    msg.error(e.message)
  } finally {
    findingSims.value = false
  }
}

async function compare() {
  const realPath = real.value.trim()
  if (!realPath) {
    report.value = null
    error.value = t('cal.err.need_real')
    msg.warning(error.value)
    return
  }
  if (!staged.value && !sim.value.trim()) {
    report.value = null
    error.value = t('cal.err.need_sim')
    msg.warning(error.value)
    return
  }
  loading.value = true
  error.value = ''
  try {
    if (staged.value) {
      const form = new FormData()
      form.append('real', realPath)
      form.append('file', staged.value, uploadName.value || 'runs.jsonl')
      report.value = await api.upload('/api/calibrate/upload', form)
    } else {
      report.value = await api.post('/api/calibrate', { real: realPath, sim: sim.value.trim() })
    }
  } catch (e) {
    report.value = null
    error.value = e.message
    msg.error(e.message)
  } finally {
    loading.value = false
  }
}

function applyQuery() {
  const nextReal = qstr(route.query.real)
  const nextSim = qstr(route.query.sim)
  if (nextReal) real.value = nextReal
  if (nextSim) {
    clearUpload()
    sim.value = nextSim
  }
  if (real.value.trim() && sim.value.trim()) compare()
}
watch(() => route.query.real + '\n' + route.query.sim, (v, prev) => {
  if (v === prev) return
  applyQuery()
})
onMounted(() => { if (real.value.trim() && sim.value.trim()) compare() })
</script>

<style scoped>
.roots { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.root { text-align: left; background: #26262B; border: 1px solid #2E2E34; color: inherit; border-radius: 10px; padding: 8px 12px; cursor: pointer; }
.root:hover, .root.on { border-color: #D97757; }
.sim-label { margin-top: 16px; }
.head { align-items: flex-start; gap: 16px; }
.head h3 { margin: 0; }
.paths { margin-top: 10px; overflow-wrap: anywhere; }
.table-wrap { overflow-x: auto; }
.fights { width: 100%; border-collapse: collapse; font-size: 13px; }
.fights th { text-align: left; color: #9C978F; font-weight: 600; padding: 6px 8px; white-space: nowrap; }
.fights td { padding: 8px; border-top: 1px solid #2A2A30; vertical-align: middle; }
.fights tr.gap td { background: rgba(224, 168, 108, .12); color: #F3E6D4; }
.fights tr.unmatched td, .fights tr.quiet td { color: #6E6A64; background: rgba(110, 106, 100, .08); }
.enc { max-width: 220px; overflow-wrap: anywhere; }
.reason { color: #8A857E; }
.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 650; background: #26262B; color: #B9B4AC; }
.badge.gap { background: rgba(224, 168, 108, .22); color: #E0A86C; }
.strip { width: 132px; height: 22px; display: block; }
.track { fill: #2A2A30; }
.whisker { fill: rgba(185, 180, 172, .45); }
.band { fill: #C9603F; }
.mark { stroke: #F0A486; fill: #F0A486; stroke-width: 1.6; }
.mark.gap { stroke: #E0A86C; fill: #E0A86C; }
.state { text-align: center; }
.state .big { font-size: 15px; color: #B9B4AC; margin-bottom: 8px; }
.state .detail { color: #CFCAC2; font-size: 13.5px; line-height: 1.55; text-align: left; }
.hint.warn { color: #E0A86C; }
.page > .panel { margin-top: 16px; }
.page > .panel:first-child { margin-top: 0; }
</style>
