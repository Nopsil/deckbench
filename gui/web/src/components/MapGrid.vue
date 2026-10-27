<template>
  <div v-if="map && (rows.length || map.boss)" class="wrap">
    <div v-for="r in rowNums" :key="r" class="mrow">
      <span class="rn">{{ r }}</span>
      <span v-for="c in cols" :key="r + '-' + c" class="cell" :class="cellClass(c, r)" :title="tip(c, r)">{{ glyph(c, r) }}</span>
    </div>
    <div class="legend">
      <span v-for="k in legend" :key="k"><b>{{ short(k) }}</b> {{ t('mp.' + k) }}</span>
    </div>
  </div>
  <div v-else class="hint">{{ t('common.none') }}</div>
</template>

<script setup>
import { computed } from 'vue'
import { t } from '../i18n'

const props = defineProps({
  map: { type: Object, default: null },
  path: { type: Array, default: () => [] },
})
const SHORT = { Monster: 'M', Elite: 'E', Unknown: '?', Shop: '$', RestSite: 'R', Treasure: 'T', Boss: 'B', Ancient: 'A', Unassigned: '.' }
const legend = ['Monster', 'Elite', 'Unknown', 'Shop', 'RestSite', 'Treasure', 'Boss', 'Ancient']
const by = computed(() => {
  const m = new Map()
  for (const row of props.map?.rows || []) for (const n of row) m.set(n.col + ',' + n.row, n)
  return m
})
const cols = computed(() => {
  const n = props.map?.cols || 0
  return Array.from({ length: n }, (_, i) => i + 1)
})
const rows = computed(() => props.map?.rows || [])
const rowNums = computed(() => {
  const set = new Set()
  for (const row of rows.value) for (const n of row) set.add(n.row)
  if (props.map?.boss?.row != null) set.add(props.map.boss.row)
  return [...set].sort((a, b) => b - a)
})
const pathSet = computed(() => new Set((props.path || []).map((p) => p.col + ',' + p.row)))
function node(c, r) {
  const n = by.value.get((c - 1) + ',' + r)
  if (n) return n
  const b = props.map?.boss
  if (b && b.col === c - 1 && b.row === r) return { type: 'Boss', col: b.col, row: b.row }
  return null
}
function onPath(c, r) { return pathSet.value.has((c - 1) + ',' + r) }
function cellClass(c, r) {
  const n = node(c, r)
  return [n?.type || '', { on: onPath(c, r) }]
}
function short(k) { return SHORT[k] || '?' }
function glyph(c, r) {
  const n = node(c, r)
  return n ? short(n.type) : ''
}
function tip(c, r) {
  const n = node(c, r)
  if (!n) return ''
  return t('mp.' + (n.type || 'Unassigned'))
}
</script>

<style scoped>
.wrap { overflow-x: auto; }
.mrow { display: flex; gap: 4px; align-items: center; margin-bottom: 4px; }
.rn { width: 18px; color: #6E6A64; font-size: 11px; text-align: right; }
.cell { width: 28px; height: 28px; border-radius: 6px; display: grid; place-items: center; font-size: 12px; font-weight: 700; background: transparent; color: transparent; }
.cell.Monster, .cell.Elite, .cell.Unknown, .cell.Shop, .cell.RestSite, .cell.Treasure, .cell.Boss, .cell.Ancient { color: #1B1B1E; }
.cell.Monster { background: #E7B299; }
.cell.Elite { background: #E07A5F; }
.cell.Unknown { background: #C7C2BA; }
.cell.Shop { background: #E6C35C; }
.cell.RestSite { background: #E08A3C; }
.cell.Treasure { background: #D4B483; }
.cell.Boss { background: #D97757; }
.cell.Ancient { background: #8FB8C9; }
.cell.on { outline: 2px solid #F2D0C4; outline-offset: 1px; }
.legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; color: #9C978F; font-size: 12px; }
.legend b { color: #EDE9E3; margin-right: 3px; }
</style>
