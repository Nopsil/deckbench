<template>
  <div class="page">
    <div class="pick row between">
      <n-select v-model:value="sel" :options="runOptions" filterable placeholder="选择一次已完成的测试" style="max-width:560px" @update:value="(v) => $router.push('/report/' + v)" />
      <div v-if="meta" class="row">
        <n-button secondary size="small" @click="openFolder"><template #icon><n-icon :component="Folder" /></template>打开文件夹</n-button>
        <n-button secondary size="small" tag="a" :href="`/api/runs/${id}/files/${meta.kind === 'batch' ? 'runs.jsonl' : 'cells.csv'}`"><template #icon><n-icon :component="Download" /></template>{{ meta.kind === 'batch' ? '原始数据' : 'cells.csv' }}</n-button>
      </div>
    </div>
    <div v-if="!id" class="panel empty"><div class="big">还没有已完成的测试</div><div>跑完一次之后，报告会出现在这里。</div></div>
    <div v-else-if="err" class="panel empty"><div class="big">{{ err }}</div></div>
    <div v-else-if="!S" class="panel empty"><n-spin /></div>
    <template v-else>
      <div class="hero">
        <div class="ht">{{ runTitle(meta) }}</div>
        <div class="row" style="flex-wrap:wrap;gap:6px;margin-top:10px">
          <span v-for="t in chips" :key="t" class="chip">{{ t }}</span>
          <span class="chip faint">{{ fmt.time(meta.created) }} · 用时 {{ fmt.secs(meta.secs) }}</span>
        </div>
      </div>

      <template v-if="meta.kind === 'batch'">
        <div class="grid g4">
          <stat label="平均层数" :value="fmt.num(S.avg_floor)" :sub="`中位 ${S.median_floor} · 最高 ${S.max_floor}`" hl />
          <stat label="到达幕 1 首领" :value="fmt.pct(S.boss1)" :bar="S.boss1" :sub="`${Math.round(S.boss1 * S.n)} / ${S.n} 局`" />
          <stat label="到达幕 2" :value="fmt.pct(S.act2)" :bar="S.act2" :sub="`到达幕 3：${fmt.pct(S.act3)}`" />
          <stat label="胜率（通关）" :value="fmt.pct(S.win)" :bar="S.win" :sub="`${S.wins} / ${S.n} 局${S.errors ? ' · 出错 ' + S.errors : ''}`" />
        </div>
        <div class="grid" style="grid-template-columns: 3fr 2fr; margin-top:16px">
          <div class="panel"><h3>层数存活曲线</h3><div class="hint" style="margin:-8px 0 6px">到达（≥）每一层的局数比例</div><chart :option="survivalOpt" :height="300" /></div>
          <div class="panel"><h3>死在哪类房间</h3><chart :option="roomOpt" :height="300" /></div>
        </div>
        <div class="grid g2" style="margin-top:16px">
          <div class="panel"><h3>死因：遭遇（前 15）</h3><chart :option="encOpt" :height="Math.max(220, S.death_by_encounter.length * 26 + 40)" /></div>
          <div class="panel"><h3>每场平均掉血</h3><chart :option="lossOpt" :height="260" />
            <h3 style="margin-top:18px">最常选的牌（前 15）</h3><chart :option="pickOpt" :height="Math.max(200, S.top_picks.length * 24 + 40)" /></div>
        </div>
      </template>

      <template v-else>
        <div class="grid g4">
          <stat label="总场数" :value="S.fights" :sub="`${S.cells.length} 个卡组×房间格子`" />
          <stat label="总体胜率（按格子场数加权）" :value="fmt.pct(S.win)" :bar="S.win" hl />
          <stat label="最高胜率格子" :value="best ? best.win.toFixed(1) + '%' : '—'" :sub="best ? `${best.deck} · ${best.room}` : ''" />
          <stat label="模拟用时" :value="fmt.secs(S.wall_secs)" />
        </div>
        <n-tabs v-model:value="tab" type="line" animated style="margin-top:16px">
          <n-tab-pane name="overview" tab="概览">
            <div class="panel"><h3>各卡组胜率（按房间）</h3><chart :option="cellOpt" :height="Math.max(280, decks.length * 34 + 70)" /></div>
            <div class="panel"><h3>格子明细</h3>
              <n-data-table :columns="cellCols" :data="S.cells" size="small" :max-height="460" :pagination="false" /></div>
          </n-tab-pane>
          <n-tab-pane name="report" tab="完整报告（report.md）">
            <div class="panel"><div v-if="md" class="md" v-html="md"></div><div v-else class="empty">没有 report.md</div></div>
          </n-tab-pane>
        </n-tabs>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NDataTable, NIcon, NSelect, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import { Folder, Download } from '@vicons/tabler'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import Stat from '../components/Stat.vue'
import Chart from '../components/Chart.vue'
import { api, store, fmt, runTitle } from '../api'
import { C, SERIES, baseChart, axis } from '../theme'

const route = useRoute()
const router = useRouter()
const msg = useMessage()
const id = computed(() => route.params.id)
const sel = ref(null)
const meta = ref(null)
const S = ref(null)
const md = ref('')
const err = ref('')
const tab = ref('overview')

const runOptions = computed(() => store.runs.filter((r) => r.status === 'done').map((r) => ({ label: `${runTitle(r)}  ·  ${fmt.time(r.created)}`, value: r.id })))
const chips = computed(() => {
  const p = meta.value?.params || {}
  if (meta.value?.kind === 'batch') {
    const t = ['整局批量', store.charName(p.char), 'A' + p.asc, p.n + ' 局', store.agentName('batch', p.agent), `种子 R${p.start || 0}起`]
    if (p.variants?.length) t.push('变体 ' + p.variants.join('+'))
    if (p.force?.length) t.push('加入 ' + p.force.map((x) => store.cardName(x)).join('、'))
    if (p.replace?.length) t.push('移除 ' + p.replace.map((x) => store.cardName(x)).join('、'))
    return t
  }
  return ['战斗实验', p.preset ? '预设 ' + p.preset : (p.decks || []).length + ' 个卡组', '每格 ' + p.fights + ' 场', store.agentName('combat', p.agent), '种子 ' + p.seed]
})

async function load() {
  S.value = null; md.value = ''; err.value = ''
  if (!id.value) {
    await store.loadRuns()
    const r = store.runs.find((x) => x.status === 'done')
    if (r) router.replace('/report/' + r.id)
    return
  }
  sel.value = id.value
  if (!store.runs.find((r) => r.id === id.value)) await store.loadRuns()
  try {
    const d = await api.get(`/api/runs/${id.value}/summary`)
    meta.value = d.meta
    S.value = d.summary
    if (!S.value) err.value = '这次测试没有可读的结果文件'
    if (d.meta.kind === 'combat' && S.value?.has_report) {
      const r = await api.get(`/api/runs/${id.value}/report`)
      md.value = DOMPurify.sanitize(marked.parse(r.markdown))
    }
  } catch (e) { err.value = e.message }
}
async function openFolder() { const r = await api.post(`/api/runs/${id.value}/open`); if (!r.ok) msg.info('结果文件夹：' + r.path) }
watch(id, load)
onMounted(load)

const survivalOpt = computed(() => {
  const s = S.value.survival
  return { ...baseChart(),
    tooltip: { ...baseChart().tooltip, trigger: 'axis', formatter: (p) => `第 ${p[0].axisValue} 层<br/>到达比例 <b>${(p[0].value * 100).toFixed(1)}%</b>` },
    xAxis: axis({ type: 'category', data: s.map((x) => x.floor), boundaryGap: false }),
    yAxis: axis({ type: 'value', max: 1, axisLabel: { color: C.muted, formatter: (v) => v * 100 + '%' } }),
    series: [{ type: 'line', data: s.map((x) => x.rate), smooth: 0.25, symbol: 'none', lineStyle: { width: 3, color: C.accent },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(217,119,87,.38)' }, { offset: 1, color: 'rgba(217,119,87,0)' }] } } }] }
})
const roomOpt = computed(() => ({ ...baseChart(),
  tooltip: { ...baseChart().tooltip, trigger: 'item', formatter: '{b}：{c} 局（{d}%）' },
  legend: { bottom: 0, textStyle: { color: C.muted }, icon: 'circle' },
  series: [{ type: 'pie', radius: ['48%', '70%'], center: ['50%', '45%'], itemStyle: { borderColor: C.surface, borderWidth: 3, borderRadius: 6 },
    label: { color: C.text, formatter: (p) => `${p.name}\n${p.percent.toFixed(0)}%`, lineHeight: 18 }, labelLine: { length: 8, length2: 8 }, data: S.value.death_by_room.map((x, i) => ({ name: x.name, value: x.count, itemStyle: { color: { 首领: C.accent, 精英: C.sand, 普通: C.blue }[x.name] || SERIES[i + 4] } })) }] }))
function hbar(items, nameFn, color, unit) {
  const d = [...items].reverse()
  return { ...baseChart(), grid: { left: 10, right: 40, top: 10, bottom: 10, containLabel: true },
    tooltip: { ...baseChart().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: axis({ type: 'value', minInterval: 1 }), yAxis: axis({ type: 'category', data: d.map(nameFn), axisLabel: { color: C.text, width: 150, overflow: 'truncate' } }),
    series: [{ type: 'bar', data: d.map((x) => x.count ?? x.value), barWidth: 14, itemStyle: { color, borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: C.muted, formatter: '{c}' + (unit || '') } }] }
}
const encOpt = computed(() => hbar(S.value.death_by_encounter, (x) => store.encName(x.name), C.accent, ' 局'))
const pickOpt = computed(() => hbar(S.value.top_picks, (x) => store.cardName(x.id), C.blue, ' 次'))
const lossOpt = computed(() => {
  const l = S.value.hp_loss
  return { ...baseChart(), tooltip: { ...baseChart().tooltip, trigger: 'axis', formatter: (p) => `${p[0].name}<br/>平均掉血 <b>${p[0].value.toFixed(1)}</b>（${l[p[0].dataIndex].n} 场）` },
    xAxis: axis({ type: 'category', data: l.map((x) => `幕${x.act}·${x.room}`), axisLabel: { color: C.muted, interval: 0, fontSize: 11 } }), yAxis: axis({ type: 'value' }),
    series: [{ type: 'bar', barWidth: 26, data: l.map((x) => ({ value: x.avg, itemStyle: { color: { 首领: C.accent, 精英: C.sand, 普通: C.blue }[x.room] || C.green, borderRadius: [6, 6, 0, 0] } })),
      label: { show: true, position: 'top', color: C.muted, formatter: (p) => p.value.toFixed(1) } }] }
})

const decks = computed(() => [...new Set((S.value?.cells || []).map((c) => c.deck + (c.act ? ` · 幕${c.act}` : '')))])
const best = computed(() => (S.value?.cells || []).filter((c) => c.win !== null && c.room !== '探针').sort((a, b) => b.win - a.win)[0])
const cellOpt = computed(() => {
  const rooms = [...new Set(S.value.cells.map((c) => c.room))]
  const key = (c) => c.deck + (c.act ? ` · 幕${c.act}` : '')
  const ds = [...decks.value].reverse()
  const col = { 普通: C.blue, 精英: C.sand, 首领: C.accent, 弱怪: C.green, 探针: C.violet }
  return { ...baseChart(), grid: { left: 10, right: 30, top: 34, bottom: 10, containLabel: true },
    legend: { top: 0, textStyle: { color: C.muted }, icon: 'roundRect' },
    tooltip: { ...baseChart().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => (v === null || v === undefined ? '—' : v.toFixed(1) + '%') },
    xAxis: axis({ type: 'value', max: 100, axisLabel: { color: C.muted, formatter: '{value}%' } }),
    yAxis: axis({ type: 'category', data: ds, axisLabel: { color: C.text, width: 190, overflow: 'truncate' } }),
    series: rooms.map((r, i) => ({ name: r, type: 'bar', barMaxWidth: 12, itemStyle: { color: col[r] || SERIES[i], borderRadius: [0, 4, 4, 0] },
      data: ds.map((d) => { const c = S.value.cells.find((x) => key(x) === d && x.room === r); return c ? c.win : null }) })) }
})
const num = (k, d = 1, suf = '') => (row) => (row[k] === null || row[k] === undefined ? '—' : row[k].toFixed(d) + suf)
const cellCols = [
  { title: '卡组', key: 'deck', width: 210, ellipsis: { tooltip: true } },
  { title: '阶段', key: 'stage', width: 80 }, { title: '幕', key: 'act', width: 50 }, { title: '房间', key: 'room', width: 66 },
  { title: '场数', key: 'n', width: 64, sorter: (a, b) => a.n - b.n },
  { title: '胜率', key: 'win', width: 120, sorter: (a, b) => a.win - b.win,
    render: (r) => h('div', { style: 'display:flex;align-items:center;gap:8px' }, [
      h('div', { style: 'width:46px;height:6px;border-radius:3px;background:#2A2A2F;overflow:hidden' }, [h('div', { style: `height:100%;width:${r.win}%;background:${C.accent}` })]),
      h('span', null, r.win === null ? '—' : r.win.toFixed(1) + '%')]) },
  { title: '平均回合', key: 'turns', render: num('turns'), sorter: (a, b) => a.turns - b.turns },
  { title: '平均掉血', key: 'hp_loss', render: num('hp_loss'), sorter: (a, b) => a.hp_loss - b.hp_loss },
  { title: '每回合输出', key: 'dpt', render: num('dpt'), sorter: (a, b) => a.dpt - b.dpt },
  { title: '循环报警', key: 'loops', width: 80 },
]
</script>

<style scoped>
.pick { margin-bottom: 18px; }
.hero { padding: 4px 2px 18px; }
.ht { font-size: 21px; font-weight: 700; }
:deep(.n-tabs .n-tab-pane) { padding-top: 14px; }
</style>
