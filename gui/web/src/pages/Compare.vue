<template>
  <div class="page" data-page="compare">
    <div class="panel">
      <div class="pickers">
        <div>
          <div class="label"><span class="tagA">A</span> {{ t('ab.baseline') }}</div>
          <n-select v-model:value="a" :options="optsA" filterable :placeholder="t('ab.pickDone')" />
        </div>
        <n-button circle secondary class="swap" :disabled="!a || !b" @click="swap"><template #icon><n-icon :component="ArrowsLeftRight" /></template></n-button>
        <div>
          <div class="label"><span class="tagB">B</span> {{ t('ab.variant') }}</div>
          <n-select v-model:value="b" :options="optsB" filterable :disabled="!a" :placeholder="t('cmp.empty')" />
        </div>
      </div>
      <div class="row between" style="margin-top:12px">
        <div class="hint" style="margin:0">{{ t('cmp.hint') }}</div>
        <div class="row">
          <n-button v-if="bundleHref" secondary tag="a" download data-action="bundle" :href="bundleHref"><template #icon><n-icon :component="FileExport" /></template>{{ t('bundle.download') }}</n-button>
          <n-button v-if="exportHref" secondary tag="a" download data-action="export" :href="exportHref"><template #icon><n-icon :component="FileExport" /></template>{{ t('export.button') }}</n-button>
        </div>
      </div>
    </div>

    <div v-if="err" class="panel empty"><div class="big">{{ err }}</div></div>
    <div v-else-if="loading" class="panel empty"><n-spin /><div>{{ t('cmp.loading') }}</div></div>
    <div v-else-if="!R" class="panel empty"><div class="big">{{ t('cmp.empty') }}</div><div>{{ t('cmp.emptyHint') }}</div></div>

    <template v-else>
      <div v-if="R.partial || (R.a && R.a.partial) || (R.b && R.b.partial)" class="panel hint warn" data-partial>{{ t('run.partialHint') }}</div>
      <div class="grid g2">
        <div class="side A"><span class="tagA">A</span><div><div class="st">{{ runTitle(R.a) }}</div><div class="sp">{{ fmt.time(R.a.created) }}</div></div></div>
        <div class="side B"><span class="tagB">B</span><div><div class="st">{{ runTitle(R.b) }}</div><div class="sp">{{ fmt.time(R.b.created) }}</div></div></div>
      </div>

      <div class="panel" style="margin-top:16px">
        <h3>{{ t('cmp.cells') }}</h3>
        <div v-if="!cellRows.length" class="empty"><div class="big">{{ t('cmp.noCells') }}</div></div>
        <table v-else class="cmp" data-table="cells">
          <thead>
            <tr>
              <th>{{ t('col.deck') }}</th>
              <th>{{ t('col.act') }}</th>
              <th>{{ t('col.room') }}</th>
              <th>{{ t('cmp.metric') }}</th>
              <th>A</th>
              <th>B</th>
              <th>{{ t('cmp.delta') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in cellRows" :key="row.key" :data-metric="row.metric" :data-sig="row.significant === true ? '1' : '0'">
              <td>{{ row.deck }}</td>
              <td>{{ row.act }}</td>
              <td>{{ roomName(row.room) }}</td>
              <td>{{ metricName(row.metric) }}</td>
              <td class="mono">{{ fmtVal(row.metric, row.a) }}</td>
              <td class="mono">{{ fmtVal(row.metric, row.b) }}</td>
              <td class="mono delta" :class="tone(row.metric, row.delta, row.significant)">
                {{ fmtDelta(row.metric, row.delta) }}
                <span v-if="row.significant === true" class="mark">{{ t('cmp.sigMark') }}</span>
              </td>
              <td>
                <span v-if="row.significant === true" class="sig">{{ t('ab.sig') }}</span>
                <span v-else-if="row.significant === false">{{ t('ab.notSig') }}</span>
                <span v-else>—</span>
                <div v-if="row.p_value != null" class="hint">{{ t('ab.pValue', { p: fmtP(row.p_value) }) }}</div>
                <div v-if="row.sample_warning" class="hint warn">{{ t('ab.tooSmallTag') }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="panel">
        <h3>{{ t('cmp.cards') }}</h3>
        <div v-if="!cardRows.length" class="empty"><div class="big">{{ t('cmp.noCards') }}</div></div>
        <table v-else class="cmp" data-table="cards">
          <thead>
            <tr>
              <th>{{ t('col.deck') }}</th>
              <th>{{ t('cmp.card') }}</th>
              <th>A {{ t('cmp.usage') }}</th>
              <th>B {{ t('cmp.usage') }}</th>
              <th>{{ t('cmp.usage') }} Δ</th>
              <th>A {{ t('cmp.efficiency') }}</th>
              <th>B {{ t('cmp.efficiency') }}</th>
              <th>{{ t('cmp.efficiency') }} Δ</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in cardRows" :key="row.key" :data-card="row.card" :data-sig="row.usage_significant === true ? '1' : '0'">
              <td>{{ row.deck }}</td>
              <td>{{ store.cardName(row.card) }}</td>
              <td class="mono">{{ fmtVal('usage', row.a_per_fight) }}</td>
              <td class="mono">{{ fmtVal('usage', row.b_per_fight) }}</td>
              <td class="mono delta" :class="tone('usage', row.usage_delta, row.usage_significant)">
                {{ fmtDelta('usage', row.usage_delta) }}
                <span v-if="row.usage_significant === true" class="mark">{{ t('cmp.sigMark') }}</span>
              </td>
              <td class="mono">{{ fmtVal('efficiency', row.a_efficiency) }}</td>
              <td class="mono">{{ fmtVal('efficiency', row.b_efficiency) }}</td>
              <td class="mono delta" :class="tone('efficiency', row.efficiency_delta, row.efficiency_delta != null && row.efficiency_delta !== 0)">
                {{ fmtDelta('efficiency', row.efficiency_delta) }}
              </td>
              <td>
                <span v-if="row.usage_significant === true" class="sig">{{ t('ab.sig') }}</span>
                <span v-else-if="row.usage_significant === false">{{ t('ab.notSig') }}</span>
                <span v-else>—</span>
                <div v-if="row.usage_p_value != null" class="hint">{{ t('ab.pValue', { p: fmtP(row.usage_p_value) }) }}</div>
                <div v-if="row.sample_warning" class="hint warn">{{ t('ab.tooSmallTag') }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NIcon, NSelect, NSpin } from 'naive-ui'
import { ArrowsLeftRight, FileExport } from '@vicons/tabler'
import { api, store, fmt, runTitle } from '../api'
import { t, tr, lang } from '../i18n'

const route = useRoute()
const router = useRouter()
const a = ref(route.query.a || null)
const b = ref(route.query.b || null)
const R = ref(null)
const err = ref('')
const loading = ref(false)
const done = computed(() => store.runs.filter((r) => r.kind === 'combat' && (r.status === 'done' || r.status === 'cancelled')))
const label = (r) => `${runTitle(r)}  ·  ${fmt.time(r.created)}${r.status === 'cancelled' || r.partial ? ' · ' + t('run.partial') : ''}`
const optsA = computed(() => done.value.map((r) => ({ label: label(r), value: r.id })))
const optsB = computed(() => done.value.filter((r) => r.id !== a.value).map((r) => ({ label: label(r), value: r.id })))
const exportHref = computed(() => {
  if (!a.value || !b.value) return undefined
  const q = new URLSearchParams({ a: a.value, b: b.value, lang: lang.value })
  return '/api/runs/compare/export.html?' + q.toString()
})
const bundleHref = computed(() => {
  if (!a.value || !b.value) return undefined
  const q = new URLSearchParams({ a: a.value, b: b.value, lang: lang.value })
  return '/api/runs/compare/bundle?' + q.toString()
})
const METRIC_KEY = { win: 'cmp.win', timeout: 'cmp.timeout', turns: 'cmp.turns', hp_loss: 'cmp.hpLoss', dpt: 'cmp.dpt' }
const HIGHER = new Set(['win', 'dpt', 'efficiency', 'usage'])
const LOWER = new Set(['timeout', 'turns', 'hp_loss'])

function metricName(key) { return t(METRIC_KEY[key] || key) }
function roomName(room) { return tr('room.', room) }
function fmtP(p) {
  if (p === null || p === undefined) return '—'
  if (p < 0.0001) return Number(p).toExponential(2)
  return Number(p).toFixed(4)
}
function fmtVal(metric, value) {
  if (value === null || value === undefined) return '—'
  if (metric === 'win' || metric === 'timeout') return (Number(value) * 100).toFixed(1) + '%'
  return Number(value).toFixed(2)
}
function fmtDelta(metric, delta) {
  if (delta === null || delta === undefined) return '—'
  const pct = metric === 'win' || metric === 'timeout'
  const n = pct ? delta * 100 : delta
  const body = (n > 0 ? '+' : n < 0 ? '−' : '±') + Math.abs(n).toFixed(pct ? 1 : 2)
  return pct ? body + ' pp' : body
}
function tone(metric, delta, significant) {
  if (significant !== true || delta === null || delta === undefined || delta === 0) return ''
  if (HIGHER.has(metric)) return delta > 0 ? 'good' : 'bad'
  if (LOWER.has(metric)) return delta < 0 ? 'good' : 'bad'
  return ''
}
function swap() {
  const nextA = b.value
  b.value = a.value
  a.value = nextA
}

const cellRows = computed(() => {
  const rows = []
  for (const cell of (R.value && R.value.cells) || []) {
    const metrics = cell.metrics || {}
    for (const key of ['win', 'timeout', 'turns', 'hp_loss', 'dpt']) {
      const metric = metrics[key]
      if (!metric) continue
      rows.push({
        ...metric,
        key: `${cell.deck_id}|${cell.act}|${cell.room}|${key}`,
        deck: cell.deck || cell.deck_id,
        act: cell.act,
        room: cell.room,
        metric: key,
      })
    }
  }
  return rows
})
const cardRows = computed(() => ((R.value && R.value.cards) || []).map((row) => ({
  ...row,
  key: `${row.deck_id}|${row.card}`,
  deck: row.deck || row.deck_id,
})))

watch([a, b], async () => {
  router.replace({ query: { ...(a.value ? { a: a.value } : {}), ...(b.value ? { b: b.value } : {}) } })
  R.value = null
  err.value = ''
  if (!a.value || !b.value) return
  loading.value = true
  try {
    const q = new URLSearchParams({ a: a.value, b: b.value })
    R.value = await api.get('/api/runs/compare?' + q.toString())
  } catch (e) { err.value = e.message } finally { loading.value = false }
}, { immediate: true })

store.loadRuns().catch(() => {})
</script>

<style scoped>
.pickers { display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; align-items: end; }
.swap { margin-bottom: 1px; }
.tagA, .tagB { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; font-weight: 800; font-size: 12px; margin-right: 6px; }
.tagA { background: #3A3A42; color: #EDE9E3; }
.tagB { background: #D97757; color: #17171A; }
.side { display: flex; gap: 12px; align-items: flex-start; padding: 16px 18px; border-radius: 14px; background: #1E1E22; border: 1px solid #2E2E34; margin-top: 16px; }
.side.B { border-color: rgba(217,119,87,.4); }
.st { font-weight: 650; font-size: 14.5px; }
.sp { color: #8A857E; font-size: 12.5px; margin-top: 4px; }
.cmp { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.cmp th { text-align: left; color: #8A857E; font-weight: 500; font-size: 12.5px; padding: 8px 10px; border-bottom: 1px solid #2E2E34; }
.cmp td { padding: 10px; border-bottom: 1px solid #26262B; }
.cmp tr:last-child td { border-bottom: none; }
.delta.good { color: #8FBF8F; font-weight: 700; }
.delta.bad { color: #E06C6C; font-weight: 700; }
.mark { margin-left: 4px; color: #EDE9E3; }
.sig { font-weight: 650; }
.hint.warn { color: #E0A86C; }
</style>
