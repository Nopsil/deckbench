<template>
  <div class="page">
    <div class="panel">
      <div class="pickers">
        <div>
          <div class="label"><span class="tagA">A</span> 基线</div>
          <n-select v-model:value="a" :options="optsA" filterable placeholder="选一次已完成的测试" />
        </div>
        <n-button circle secondary class="swap" :disabled="!a || !b" @click="[a, b] = [b, a]"><template #icon><n-icon :component="ArrowsLeftRight" /></template></n-button>
        <div>
          <div class="label"><span class="tagB">B</span> 对照（改动后）</div>
          <n-select v-model:value="b" :options="optsB" filterable :disabled="!a" placeholder="和 A 同类型的测试" />
        </div>
      </div>
      <div class="hint">最适合：两次整局批量，用同一批种子（同角色、进阶、局数、起始种子），只差强制加入/移除的牌或变体 —— 这样按种子配对，差值的误差最小。</div>
    </div>

    <div v-if="err" class="panel empty"><div class="big">{{ err }}</div></div>
    <div v-else-if="loading" class="panel empty"><n-spin /></div>
    <div v-else-if="!R" class="panel empty"><div class="big">选两次测试开始对比</div><div>在「新建测试」里用同一批种子跑一组基线和一组加牌，就可以在这里比较。</div></div>

    <template v-else-if="R.kind === 'batch'">
      <div class="grid g2">
        <div class="side A"><span class="tagA">A</span><div><div class="st">{{ runTitle(R.a) }}</div><div class="sp">{{ R.result.a.n }} 局有效 · {{ fmt.time(R.a.created) }}</div></div></div>
        <div class="side B"><span class="tagB">B</span><div><div class="st">{{ runTitle(R.b) }}</div><div class="sp">{{ R.result.b.n }} 局有效 · {{ fmt.time(R.b.created) }}</div></div></div>
      </div>
      <div v-if="floorRow" class="grid g4" style="margin-top:16px">
        <stat label="平均层数差（B − A）" :value="signed(floorRow.diff, 2)" :sub="`95% 区间 ± ${floorRow.ci95?.toFixed(2)} · ${floorRow.significant ? '显著' : '不显著'}`" :hl="floorRow.significant" />
        <stat v-for="r in rateRows.slice(0, 3)" :key="r.key" :label="r.name + '差'" :value="signed(r.diff * 100, 1) + ' pp'" :sub="`± ${(r.ci95 * 100).toFixed(1)} pp · ${r.significant ? '显著' : '不显著'}`" :hl="r.significant" />
      </div>
      <div class="grid" style="grid-template-columns: 1fr 1fr; margin-top:16px">
        <div class="panel"><h3>比例指标差值（百分点，误差线 = 95% 区间）</h3><chart :option="diffOpt" :height="300" />
          <div class="legend"><span><i style="background:#8FBF8F"></i>显著变好</span><span><i style="background:#E06C6C"></i>显著变差</span><span><i style="background:#5A5A62"></i>不显著</span></div></div>
        <div class="panel"><h3>并排数值</h3>
          <table class="cmp">
            <thead><tr><th>指标</th><th>A</th><th>B</th><th>差值（B − A）</th><th></th></tr></thead>
            <tbody>
              <tr v-for="r in R.result.rows" :key="r.key">
                <td>{{ r.name }}</td>
                <td>{{ r.pct ? fmt.pct(r.a) : fmt.num(r.a) }}</td>
                <td>{{ r.pct ? fmt.pct(r.b) : fmt.num(r.b) }}</td>
                <td class="mono">{{ r.diff === undefined ? '—' : (r.pct ? signed(r.diff * 100, 1) + ' ± ' + (r.ci95 * 100).toFixed(1) + ' pp' : signed(r.diff, 2) + ' ± ' + r.ci95.toFixed(2)) }}</td>
                <td><n-tag v-if="r.diff !== undefined" size="small" :bordered="false" :type="r.significant ? (r.diff > 0 ? 'success' : 'error') : 'default'">{{ r.significant ? '显著' : '不显著' }}</n-tag></td>
              </tr>
              <tr><td>幕 1 普通战每场掉血</td><td>{{ fmt.num(R.result.a.mon_loss_a1, 1) }}</td><td>{{ fmt.num(R.result.b.mon_loss_a1, 1) }}</td><td class="mono">{{ R.result.a.mon_loss_a1 != null && R.result.b.mon_loss_a1 != null ? signed(R.result.b.mon_loss_a1 - R.result.a.mon_loss_a1, 1) : '—' }}</td><td></td></tr>
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
      <div v-if="!R.result.rows.length" class="panel empty" style="margin-top:16px"><div class="big">两次实验没有相同的（卡组, 幕, 房间）格子</div></div>
      <template v-else>
        <div class="panel" style="margin-top:16px"><h3>各格子胜率差（B − A，百分点，误差线 = 95% 区间，两比例 z 检验）</h3>
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
import { C, baseChart, axis } from '../theme'

const route = useRoute()
const router = useRouter()
const a = ref(route.query.a || null)
const b = ref(route.query.b || null)
const R = ref(null)
const err = ref('')
const loading = ref(false)
const done = computed(() => store.runs.filter((r) => r.status === 'done'))
const label = (r) => `${r.kind === 'batch' ? '整局' : '战斗'} · ${runTitle(r)}  ·  ${fmt.time(r.created)}`
const optsA = computed(() => done.value.map((r) => ({ label: label(r), value: r.id })))
const optsB = computed(() => {
  const ra = done.value.find((r) => r.id === a.value)
  return done.value.filter((r) => r.id !== a.value && (!ra || r.kind === ra.kind)).map((r) => ({ label: label(r), value: r.id }))
})
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
  if (!r) return '样本太少，无法估计差值。'
  return r.paired ? `按种子配对：${r.n} 个共同种子（其中层数不同的 ${floorRow.value?.differ ?? '—'} 个）。显著 = 差值超出 95% 区间。`
    : '两次测试没有共同种子，按两组独立样本估计（误差会比配对大很多）。'
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
      formatter: (p) => { const r = rows[p[0].dataIndex]; return `${cats[p[0].dataIndex]}<br/>差值 <b>${signed(r.diff * 100, 1)} pp</b>（± ${(r.ci95 * 100).toFixed(1)}）<br/>${r.significant ? '显著' : '不显著'}` } },
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
const diffOpt = computed(() => diffChart(rateRows.value, (r) => r.name))
const cellDiffOpt = computed(() => diffChart(R.value.result.rows, (r) => `${r.deck} · 幕${r.act} · ${r.room}`))
const p1 = (x) => (x === null || x === undefined ? '—' : (x * 100).toFixed(1) + '%')
const cellCols = [
  { title: '卡组', key: 'deck', ellipsis: { tooltip: true } }, { title: '幕', key: 'act', width: 50 }, { title: '房间', key: 'room', width: 66 },
  { title: 'A 胜率', key: 'a', render: (r) => `${p1(r.a)}（${r.na}）` }, { title: 'B 胜率', key: 'b', render: (r) => `${p1(r.b)}（${r.nb}）` },
  { title: '差值', key: 'diff', sorter: (x, y) => x.diff - y.diff, render: (r) => h('span', { class: 'mono' }, `${signed(r.diff * 100, 1)} ± ${(r.ci95 * 100).toFixed(1)} pp`) },
  { title: '', key: 's', width: 80, render: (r) => h(NTag, { size: 'small', bordered: false, type: r.significant ? (r.diff > 0 ? 'success' : 'error') : 'default' }, { default: () => (r.significant ? '显著' : '不显著') }) },
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
