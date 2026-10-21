<template>
  <div class="page">
    <div class="pick row between">
      <n-select v-model:value="sel" :options="runOptions" filterable :placeholder="t('rep.pick')" style="max-width:560px" @update:value="(v) => $router.push('/report/' + v)" />
      <div v-if="meta" class="row">
        <n-button secondary size="small" @click="openFolder"><template #icon><n-icon :component="Folder" /></template>{{ t('common.openFolder') }}</n-button>
        <n-button secondary size="small" tag="a" :href="`/api/runs/${id}/files/${meta.kind === 'batch' ? 'runs.jsonl' : 'cells.csv'}`"><template #icon><n-icon :component="Download" /></template>{{ meta.kind === 'batch' ? t('rep.rawData') : 'cells.csv' }}</n-button>
      </div>
    </div>
    <div v-if="!id" class="panel empty"><div class="big">{{ t('rep.none') }}</div><div>{{ t('rep.noneHint') }}</div></div>
    <div v-else-if="err" class="panel empty"><div class="big">{{ err }}</div></div>
    <div v-else-if="!S" class="panel empty"><n-spin /></div>
    <template v-else>
      <div class="hero">
        <div class="ht">{{ runTitle(meta) }}</div>
        <div class="row" style="flex-wrap:wrap;gap:6px;margin-top:10px">
          <span v-for="t in chips" :key="t" class="chip">{{ t }}</span>
          <span class="chip faint">{{ fmt.time(meta.created) }} · {{ t('common.elapsed') }} {{ fmt.secs(meta.secs) }}</span>
        </div>
      </div>

      <template v-if="meta.kind === 'batch'">
        <div class="grid g4">
          <stat :label="t('rep.avgFloor')" :value="fmt.num(S.avg_floor)" :sub="t('rep.medianMax', { med: S.median_floor, max: S.max_floor })" hl />
          <stat :label="t('metric.boss1')" :value="fmt.pct(S.boss1)" :bar="S.boss1" :sub="t('rep.xOfN', { x: Math.round(S.boss1 * S.n), n: S.n })" />
          <stat :label="t('metric.act2')" :value="fmt.pct(S.act2)" :bar="S.act2" :sub="t('rep.act3Sub', { p: fmt.pct(S.act3) })" />
          <stat :label="t('rep.winRate')" :value="fmt.pct(S.win)" :bar="S.win" :sub="t('rep.xOfN', { x: S.wins, n: S.n }) + (S.errors ? ' · ' + t('rep.errorsN', { n: S.errors }) : '')" />
        </div>
        <div class="grid" style="grid-template-columns: 3fr 2fr; margin-top:16px">
          <div class="panel"><h3>{{ t('rep.survival') }}</h3><div class="hint" style="margin:-8px 0 6px">{{ t('rep.survivalHint') }}</div><chart :option="survivalOpt" :height="300" /></div>
          <div class="panel"><h3>{{ t('rep.deathRoom') }}</h3><chart :option="roomOpt" :height="300" /></div>
        </div>
        <div class="grid g2" style="margin-top:16px">
          <div class="panel"><h3>{{ t('rep.deathEnc') }}</h3><chart :option="encOpt" :height="Math.max(220, S.death_by_encounter.length * 26 + 40)" /></div>
          <div class="panel"><h3>{{ t('rep.hpLoss') }}</h3><chart :option="lossOpt" :height="260" />
            <h3 style="margin-top:18px">{{ t('rep.topPicks') }}</h3><chart :option="pickOpt" :height="Math.max(200, S.top_picks.length * 24 + 40)" /></div>
        </div>
      </template>

      <template v-else>
        <div class="grid g4">
          <stat :label="t('rep.totalFights')" :value="S.fights" :sub="t('rep.cellsSub', { n: S.cells.length })" />
          <stat :label="t('rep.overallWin')" :value="fmt.pct(S.win)" :bar="S.win" hl />
          <stat :label="t('rep.bestCell')" :value="best ? best.win.toFixed(1) + '%' : '—'" :sub="best ? `${best.deck} · ${tr('room.', best.room)}` : ''" />
          <stat :label="t('rep.simTime')" :value="fmt.secs(S.wall_secs)" />
        </div>
        <n-tabs v-model:value="tab" type="line" animated style="margin-top:16px">
          <n-tab-pane name="overview" :tab="t('rep.overview')">
            <div class="panel"><h3>{{ t('rep.deckWin') }}</h3><chart :option="cellOpt" :height="Math.max(280, decks.length * 34 + 70)" /></div>
            <div class="panel"><h3>{{ t('rep.cellDetail') }}</h3>
              <n-data-table :columns="cellCols" :data="S.cells" size="small" :max-height="460" :pagination="false" /></div>
          </n-tab-pane>
          <n-tab-pane name="report" :tab="t('rep.fullReport')">
            <div class="panel"><div v-if="md && lang !== 'zhs'" class="hint" style="margin:0 0 12px">{{ t('rep.reportZhOnly') }}</div><div v-if="md" class="md" v-html="md"></div><div v-else class="empty">{{ t('rep.noReport') }}</div></div>
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
import { t, tr, lang, joinList } from '../i18n'
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
    const x = [t('kind.batch'), store.charName(p.char), 'A' + p.asc, t('chip.nRuns', { n: p.n }), store.agentName('batch', p.agent),
      p.game_seed ? t('chip.seed', { s: p.game_seed }) : t('chip.seedFrom', { s: 'R' + (p.start || 0) })]
    x.push(t('chip.style', { style: store.styleName(p.style) }))
    if (p.variants?.length) x.push(t('chip.variant', { v: p.variants.join('+') }))
    if (p.force?.length) x.push(t('chip.add', { cards: joinList(p.force.map((c) => store.cardName(c))) }))
    if (p.replace?.length) x.push(t('chip.remove', { cards: joinList(p.replace.map((c) => store.cardName(c))) }))
    return x
  }
  return [t('kind.combat'), p.preset ? t('chip.preset', { id: p.preset }) : t('nt.nDecks', { n: (p.decks || []).length }), t('chip.perCell', { n: p.fights }), store.agentName('combat', p.agent), t('chip.seed', { s: p.seed })]
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
    if (!S.value) err.value = t('rep.noResult')
    if (d.meta.kind === 'combat' && S.value?.has_report) {
      const r = await api.get(`/api/runs/${id.value}/report`)
      md.value = DOMPurify.sanitize(marked.parse(r.markdown))
    }
  } catch (e) { err.value = e.message }
}
async function openFolder() { const r = await api.post(`/api/runs/${id.value}/open`); if (!r.ok) msg.info(t('common.resultFolder') + r.path) }
watch(id, load)
onMounted(load)

const survivalOpt = computed(() => {
  const s = S.value.survival
  return { ...baseChart(),
    tooltip: { ...baseChart().tooltip, trigger: 'axis', formatter: (p) => `${t('rep.floorN', { n: p[0].axisValue })}<br/>${t('rep.reachRate')} <b>${(p[0].value * 100).toFixed(1)}%</b>` },
    xAxis: axis({ type: 'category', data: s.map((x) => x.floor), boundaryGap: false }),
    yAxis: axis({ type: 'value', max: 1, axisLabel: { color: C.muted, formatter: (v) => v * 100 + '%' } }),
    series: [{ type: 'line', data: s.map((x) => x.rate), smooth: 0.25, symbol: 'none', lineStyle: { width: 3, color: C.accent },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(217,119,87,.38)' }, { offset: 1, color: 'rgba(217,119,87,0)' }] } } }] }
})
const roomOpt = computed(() => ({ ...baseChart(),
  tooltip: { ...baseChart().tooltip, trigger: 'item', formatter: (p) => t('rep.pieTip', { name: p.name, n: p.value, p: p.percent.toFixed(1) }) },
  legend: { bottom: 0, textStyle: { color: C.muted }, icon: 'circle' },
  series: [{ type: 'pie', radius: ['48%', '70%'], center: ['50%', '45%'], itemStyle: { borderColor: C.surface, borderWidth: 3, borderRadius: 6 },
    label: { color: C.text, formatter: (p) => `${p.name}\n${p.percent.toFixed(0)}%`, lineHeight: 18 }, labelLine: { length: 8, length2: 8 }, data: S.value.death_by_room.map((x, i) => ({ name: tr('room.', x.name), value: x.count, itemStyle: { color: { 首领: C.accent, 精英: C.sand, 普通: C.blue }[x.name] || SERIES[i + 4] } })) }] }))
function hbar(items, nameFn, color, unit) {
  const d = [...items].reverse()
  return { ...baseChart(), grid: { left: 10, right: 40, top: 10, bottom: 10, containLabel: true },
    tooltip: { ...baseChart().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: axis({ type: 'value', minInterval: 1 }), yAxis: axis({ type: 'category', data: d.map(nameFn), axisLabel: { color: C.text, width: 150, overflow: 'truncate' } }),
    series: [{ type: 'bar', data: d.map((x) => x.count ?? x.value), barWidth: 14, itemStyle: { color, borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: C.muted, formatter: '{c}' + (unit || '') } }] }
}
const encOpt = computed(() => hbar(S.value.death_by_encounter, (x) => store.encName(x.name), C.accent, t('unit.runs')))
const pickOpt = computed(() => hbar(S.value.top_picks, (x) => store.cardName(x.id), C.blue, t('unit.times')))
const lossOpt = computed(() => {
  const l = S.value.hp_loss
  return { ...baseChart(), tooltip: { ...baseChart().tooltip, trigger: 'axis', formatter: (p) => `${p[0].name}<br/>${t('rep.avgHpLoss')} <b>${p[0].value.toFixed(1)}</b> ${t('rep.nFightsParen', { n: l[p[0].dataIndex].n })}` },
    xAxis: axis({ type: 'category', data: l.map((x) => `${t('rep.actN', { n: x.act })}\n${tr('room.', x.room)}`), axisLabel: { color: C.muted, interval: 0, fontSize: 11 } }), yAxis: axis({ type: 'value' }),
    series: [{ type: 'bar', barWidth: 26, data: l.map((x) => ({ value: x.avg, itemStyle: { color: { 首领: C.accent, 精英: C.sand, 普通: C.blue }[x.room] || C.green, borderRadius: [6, 6, 0, 0] } })),
      label: { show: true, position: 'top', color: C.muted, formatter: (p) => p.value.toFixed(1) } }] }
})

const deckKey = (c) => c.deck + (c.act ? ` · ${t('rep.actN', { n: c.act })}` : '')
const decks = computed(() => [...new Set((S.value?.cells || []).map(deckKey))])
const best = computed(() => (S.value?.cells || []).filter((c) => c.win !== null && c.room !== '探针').sort((a, b) => b.win - a.win)[0])
const cellOpt = computed(() => {
  const rooms = [...new Set(S.value.cells.map((c) => c.room))]
  const key = deckKey
  const ds = [...decks.value].reverse()
  const col = { 普通: C.blue, 精英: C.sand, 首领: C.accent, 弱怪: C.green, 探针: C.violet }
  return { ...baseChart(), grid: { left: 10, right: 30, top: 34, bottom: 10, containLabel: true },
    legend: { top: 0, textStyle: { color: C.muted }, icon: 'roundRect' },
    tooltip: { ...baseChart().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => (v === null || v === undefined ? '—' : v.toFixed(1) + '%') },
    xAxis: axis({ type: 'value', max: 100, axisLabel: { color: C.muted, formatter: '{value}%' } }),
    yAxis: axis({ type: 'category', data: ds, axisLabel: { color: C.text, width: 190, overflow: 'truncate' } }),
    series: rooms.map((r, i) => ({ name: tr('room.', r), type: 'bar', barMaxWidth: 12, itemStyle: { color: col[r] || SERIES[i], borderRadius: [0, 4, 4, 0] },
      data: ds.map((d) => { const c = S.value.cells.find((x) => key(x) === d && x.room === r); return c ? c.win : null }) })) }
})
const num = (k, d = 1, suf = '') => (row) => (row[k] === null || row[k] === undefined ? '—' : row[k].toFixed(d) + suf)
const cellCols = [
  { title: () => t('col.deck'), key: 'deck', width: 210, ellipsis: { tooltip: true } },
  { title: () => t('col.stage'), key: 'stage', width: 90, render: (r) => tr('stage.', r.stage) }, { title: () => t('col.act'), key: 'act', width: 56 },
  { title: () => t('col.room'), key: 'room', width: 76, render: (r) => tr('room.', r.room) },
  { title: () => t('col.fights'), key: 'n', width: 72, sorter: (a, b) => a.n - b.n },
  { title: () => t('col.win'), key: 'win', width: 120, sorter: (a, b) => a.win - b.win,
    render: (r) => h('div', { style: 'display:flex;align-items:center;gap:8px' }, [
      h('div', { style: 'width:46px;height:6px;border-radius:3px;background:#2A2A2F;overflow:hidden' }, [h('div', { style: `height:100%;width:${r.win}%;background:${C.accent}` })]),
      h('span', null, r.win === null ? '—' : r.win.toFixed(1) + '%')]) },
  { title: () => t('col.turns'), key: 'turns', render: num('turns'), sorter: (a, b) => a.turns - b.turns },
  { title: () => t('col.hpLoss'), key: 'hp_loss', render: num('hp_loss'), sorter: (a, b) => a.hp_loss - b.hp_loss },
  { title: () => t('col.dpt'), key: 'dpt', render: num('dpt'), sorter: (a, b) => a.dpt - b.dpt },
  { title: () => t('col.loops'), key: 'loops', width: 90 },
]
</script>

<style scoped>
.pick { margin-bottom: 18px; }
.hero { padding: 4px 2px 18px; }
.ht { font-size: 21px; font-weight: 700; }
:deep(.n-tabs .n-tab-pane) { padding-top: 14px; }
</style>
