<template>
  <div class="page">
    <div class="panel">
      <div class="pickers">
        <div>
          <div class="label"><span class="tagA">A</span> {{ t('ab.baseline') }}</div>
          <n-select v-model:value="a" :options="optsA" filterable :placeholder="t('ab.pickDone')" />
        </div>
        <n-button circle secondary class="swap" :disabled="!a || !b" @click="[a, b] = [b, a]"><template #icon><n-icon :component="ArrowsLeftRight" /></template></n-button>
        <div>
          <div class="label"><span class="tagB">B</span> {{ t('ab.variant') }}</div>
          <n-select v-model:value="b" :options="optsB" filterable :disabled="!a" :placeholder="t('ab.sameKind')" />
        </div>
      </div>
      <div class="hint">{{ t('ab.bestFor') }}</div>
    </div>

    <div v-if="err" class="panel empty"><div class="big">{{ err }}</div></div>
    <div v-else-if="loading" class="panel empty"><n-spin /></div>
    <div v-else-if="!R" class="panel empty"><div class="big">{{ t('ab.empty') }}</div><div>{{ t('ab.emptyHint') }}</div></div>

    <template v-else-if="R.kind === 'batch'">
      <div class="grid g2">
        <div class="side A"><span class="tagA">A</span><div><div class="st">{{ runTitle(R.a) }}</div><div class="sp">{{ t('ab.validRuns', { n: R.result.a.n }) }} · {{ fmt.time(R.a.created) }}</div></div></div>
        <div class="side B"><span class="tagB">B</span><div><div class="st">{{ runTitle(R.b) }}</div><div class="sp">{{ t('ab.validRuns', { n: R.result.b.n }) }} · {{ fmt.time(R.b.created) }}</div></div></div>
      </div>
      <div v-if="floorRow" class="grid g4" style="margin-top:16px">
        <stat :label="t('ab.floorDiff')" :value="signed(floorRow.diff, 2)" :sub="t('ab.ci95', { v: floorRow.ci95?.toFixed(2) }) + ' · ' + sig(floorRow)" :hl="floorRow.significant" />
        <stat v-for="r in rateRows.slice(0, 3)" :key="r.key" :label="t('ab.diffOf', { name: mname(r) })" :value="signed(r.diff * 100, 1) + ' pp'" :sub="`± ${(r.ci95 * 100).toFixed(1)} pp · ${sig(r)}`" :hl="r.significant" />
      </div>
      <div class="grid" style="grid-template-columns: 1fr 1fr; margin-top:16px">
        <div class="panel"><h3>{{ t('ab.rateDiffTitle') }}</h3><chart :option="diffOpt" :height="300" />
          <div class="legend"><span><i style="background:#8FBF8F"></i>{{ t('ab.better') }}</span><span><i style="background:#E06C6C"></i>{{ t('ab.worse') }}</span><span><i style="background:#5A5A62"></i>{{ t('ab.notSig') }}</span></div></div>
        <div class="panel"><h3>{{ t('ab.sideBySide') }}</h3>
          <table class="cmp">
            <thead><tr><th>{{ t('ab.metric') }}</th><th>A</th><th>B</th><th>{{ t('ab.diffBA') }}</th><th></th></tr></thead>
            <tbody>
              <tr v-for="r in R.result.rows" :key="r.key">
                <td>{{ mname(r) }}</td>
                <td>{{ r.pct ? fmt.pct(r.a) : fmt.num(r.a) }}</td>
                <td>{{ r.pct ? fmt.pct(r.b) : fmt.num(r.b) }}</td>
                <td class="mono">{{ r.diff === undefined ? '—' : (r.pct ? signed(r.diff * 100, 1) + ' ± ' + (r.ci95 * 100).toFixed(1) + ' pp' : signed(r.diff, 2) + ' ± ' + r.ci95.toFixed(2)) }}</td>
                <td><n-tag v-if="r.diff !== undefined" size="small" :bordered="false" :type="r.significant ? (r.diff > 0 ? 'success' : 'error') : 'default'">{{ sig(r) }}</n-tag></td>
              </tr>
              <tr><td>{{ t('ab.monLossA1') }}</td><td>{{ fmt.num(R.result.a.mon_loss_a1, 1) }}</td><td>{{ fmt.num(R.result.b.mon_loss_a1, 1) }}</td><td class="mono">{{ R.result.a.mon_loss_a1 != null && R.result.b.mon_loss_a1 != null ? signed(R.result.b.mon_loss_a1 - R.result.a.mon_loss_a1, 1) : '—' }}</td><td></td></tr>
            </tbody>
          </table>
          <div class="hint">{{ pairNote }}</div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="grid g2">
        <div class="side A"><span class="tagA">A</span><div><div class="st">{{ runTitle(R.a) }}</div></div></div>
        <div class="side B"><span class="tagB">B</span><div><div class="st">{{ runTitle(R.b) }}</div></div></div>
      </div>
      <div v-if="!R.result.rows.length" class="panel empty" style="margin-top:16px"><div class="big">{{ t('ab.noCommonCells') }}</div></div>
      <template v-else>
        <div class="panel" style="margin-top:16px"><h3>{{ t('ab.cellDiffTitle') }}</h3>
          <chart :option="cellDiffOpt" :height="Math.max(260, R.result.rows.length * 30 + 60)" /></div>
        <div class="panel"><n-data-table :columns="cellCols" :data="R.result.rows" size="small" :max-height="460" /></div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, h, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NDataTable, NIcon, NSelect, NSpin, NTag } from 'naive-ui'
import { ArrowsLeftRight } from '@vicons/tabler'
import Stat from '../components/Stat.vue'
import Chart from '../components/Chart.vue'
import { api, store, fmt, runTitle } from '../api'
import { t, tr } from '../i18n'
import { C, baseChart, axis } from '../theme'

const route = useRoute()
const router = useRouter()
const a = ref(route.query.a || null)
const b = ref(route.query.b || null)
const R = ref(null)
const err = ref('')
const loading = ref(false)
const done = computed(() => store.runs.filter((r) => r.status === 'done'))
const label = (r) => `${r.kind === 'batch' ? t('ab.kindBatch') : t('ab.kindCombat')} · ${runTitle(r)}  ·  ${fmt.time(r.created)}`
const optsA = computed(() => done.value.map((r) => ({ label: label(r), value: r.id })))
const optsB = computed(() => {
  const ra = done.value.find((r) => r.id === a.value)
  return done.value.filter((r) => r.id !== a.value && (!ra || r.kind === ra.kind)).map((r) => ({ label: label(r), value: r.id }))
})
const sig = (r) => (r.significant ? t('ab.sig') : t('ab.notSig'))
const mname = (r) => tr('metric.', r.key)
const signed = (x, d) => (x === undefined || x === null ? '—' : (x > 0 ? '+' : x < 0 ? '−' : '±') + Math.abs(x).toFixed(d))

watch([a, b], async () => {
  router.replace({ query: { ...(a.value ? { a: a.value } : {}), ...(b.value ? { b: b.value } : {}) } })
  R.value = null; err.value = ''
  if (!a.value || !b.value) return
  loading.value = true
  try { R.value = await api.get(`/api/ab?a=${a.value}&b=${b.value}`) } catch (e) { err.value = e.message } finally { loading.value = false }
}, { immediate: true })

const floorRow = computed(() => R.value?.result.rows.find((r) => r.key === 'floor' && r.diff !== undefined))
const rateRows = computed(() => (R.value?.result.rows || []).filter((r) => r.pct && r.diff !== undefined))
const pairNote = computed(() => {
  const r = R.value?.result.rows.find((x) => x.diff !== undefined)
  if (!r) return t('ab.tooFew')
  return r.paired ? t('ab.paired', { n: r.n, d: floorRow.value?.differ ?? '—' })
    : t('ab.unpaired')
})
const colorOf = (r) => (r.significant ? (r.diff > 0 ? C.green : C.red) : '#5A5A62')

function diffChart(items, nameFn) {
  const cats = items.map(nameFn).reverse()
  const rows = [...items].reverse()
  const lo = Math.max(-100, Math.min(0, ...rows.map((r) => (r.diff - r.ci95) * 100)))
  const hi = Math.min(100, Math.max(0, ...rows.map((r) => (r.diff + r.ci95) * 100)))
  const pad = Math.max(2, (hi - lo) * 0.06)
  return { ...baseChart(), grid: { left: 10, right: 40, top: 16, bottom: 20, containLabel: true },
    tooltip: { ...baseChart().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (p) => { const r = rows[p[0].dataIndex]; return `${cats[p[0].dataIndex]}<br/>${t('ab.diff')} <b>${signed(r.diff * 100, 1)} pp</b> (± ${(r.ci95 * 100).toFixed(1)})<br/>${sig(r)}` } },
    xAxis: axis({ type: 'value', min: Math.floor(lo - pad), max: Math.ceil(hi + pad), axisLabel: { color: C.muted, hideOverlap: true, formatter: (v) => (v > 0 ? '+' : '') + v } , name: 'pp', nameTextStyle: { color: C.faint } }),
    yAxis: axis({ type: 'category', data: cats, axisLabel: { color: C.text, width: 200, overflow: 'truncate' } }),
    series: [
      { type: 'bar', barWidth: 16, data: rows.map((r) => ({ value: +(r.diff * 100).toFixed(2), itemStyle: { color: colorOf(r), borderRadius: 4 } })),
        markLine: { symbol: 'none', silent: true, lineStyle: { color: C.faint, type: 'solid' }, data: [{ xAxis: 0 }], label: { show: false } } },
      { type: 'custom', z: 10, clip: true, data: rows.map((r, i) => [i, (r.diff - r.ci95) * 100, (r.diff + r.ci95) * 100]),
        renderItem: (params, api) => {
          const y = api.coord([0, api.value(0)])[1]
          const lo = api.coord([api.value(1), api.value(0)])[0]
          const hi = api.coord([api.value(2), api.value(0)])[0]
          const st = { stroke: '#EDE9E3', lineWidth: 1.5 }
          return { type: 'group', children: [
            { type: 'line', shape: { x1: lo, y1: y, x2: hi, y2: y }, style: st },
            { type: 'line', shape: { x1: lo, y1: y - 5, x2: lo, y2: y + 5 }, style: st },
            { type: 'line', shape: { x1: hi, y1: y - 5, x2: hi, y2: y + 5 }, style: st }] }
        } }] }
}
const diffOpt = computed(() => diffChart(rateRows.value, mname))
const cellDiffOpt = computed(() => diffChart(R.value.result.rows, (r) => `${r.deck} · ${t('rep.actN', { n: r.act })} · ${tr('room.', r.room)}`))
const p1 = (x) => (x === null || x === undefined ? '—' : (x * 100).toFixed(1) + '%')
const cellCols = [
  { title: () => t('col.deck'), key: 'deck', ellipsis: { tooltip: true } }, { title: () => t('col.act'), key: 'act', width: 56 },
  { title: () => t('col.room'), key: 'room', width: 76, render: (r) => tr('room.', r.room) },
  { title: () => t('ab.winA'), key: 'a', render: (r) => `${p1(r.a)} (${r.na})` }, { title: () => t('ab.winB'), key: 'b', render: (r) => `${p1(r.b)} (${r.nb})` },
  { title: () => t('ab.diff'), key: 'diff', sorter: (x, y) => x.diff - y.diff, render: (r) => h('span', { class: 'mono' }, `${signed(r.diff * 100, 1)} ± ${(r.ci95 * 100).toFixed(1)} pp`) },
  { title: '', key: 's', width: 80, render: (r) => h(NTag, { size: 'small', bordered: false, type: r.significant ? (r.diff > 0 ? 'success' : 'error') : 'default' }, { default: () => sig(r) }) },
]
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
.cmp td.mono { white-space: nowrap; }
.cmp td { padding: 11px 10px; border-bottom: 1px solid #26262B; }
.cmp tr:last-child td { border-bottom: none; }
.legend { display: flex; gap: 18px; justify-content: center; font-size: 12px; color: #8A857E; margin-top: 4px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
</style>
