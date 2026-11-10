<template>
  <div data-card-impact :data-impact-status="doc.status || ''">
    <div v-if="doc.scaled" class="hint warn">{{ t('deck.impactScaled', { n: doc.fights, cap: doc.cap }) }}</div>
    <div v-if="doc.partial" class="hint warn" data-partial>{{ t('run.partialHint') }}</div>
    <p class="hint">{{ t('deck.impactNote') }}</p>
    <div v-if="baseline" class="hint" data-impact-baseline>
      {{ t('deck.impactBaseline') }} · {{ pct(baseline.win_rate) }} · {{ plain(baseline.hp_lost) }} · {{ plain(baseline.turns) }}
      · n={{ baseline.n }}
    </div>
    <div v-if="!rows.length" class="hint">{{ t('deck.impactEmpty') }}</div>
    <div v-else class="scroll">
      <table data-table="card-impact" :data-sort-key="sortKey" :data-sort-dir="sortDir">
        <thead>
          <tr>
            <th>{{ t('deck.impactCard') }}</th>
            <th>{{ t('deck.impactChange') }}</th>
            <th>{{ t('deck.impactN') }}</th>
            <th><button type="button" data-sort="delta_win" @click="toggle('delta_win')">{{ t('deck.impactDeltaWin') }}</button></th>
            <th><button type="button" data-sort="delta_hp_lost" @click="toggle('delta_hp_lost')">{{ t('deck.impactDeltaHp') }}</button></th>
            <th><button type="button" data-sort="delta_turns" @click="toggle('delta_turns')">{{ t('deck.impactDeltaTurns') }}</button></th>
            <th>{{ t('deck.impactNoisy') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in sorted"
            :key="row.change + ':' + row.card_id + ':' + (row.upgrade ? '1' : '0')"
            data-impact-row
            :data-card="row.card_id"
            :data-change="row.change"
            :data-noisy="row.noisy ? '1' : '0'"
            :data-noisy-reason="row.noisy_reason || ''"
          >
            <td>{{ name(row) }}</td>
            <td>{{ change(row) }}</td>
            <td>{{ row.n }}</td>
            <td :data-delta-win="row.delta_win">{{ signedPct(row.delta_win) }} <span v-if="row.win_effect" class="effect">{{ effect(row.win_effect) }}</span></td>
            <td :data-delta-hp="row.delta_hp_lost">{{ signedNum(row.delta_hp_lost) }} <span v-if="row.hp_effect" class="effect">{{ effect(row.hp_effect) }}</span></td>
            <td :data-delta-turns="row.delta_turns">{{ signedNum(row.delta_turns) }}</td>
            <td>{{ flag(row) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="err" class="hint warn">{{ err }}</div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { t, lang } from '../i18n'

const props = defineProps({
  jobId: { type: String, default: '' },
  deckId: { type: String, default: '' },
})

const doc = ref({})
const err = ref('')
const sortKey = ref('delta_win')
const sortDir = ref('desc')
let timer = null

const rows = computed(() => (Array.isArray(doc.value.rows) ? doc.value.rows : []))
const baseline = computed(() => (doc.value.baseline && typeof doc.value.baseline === 'object' ? doc.value.baseline : null))
const sorted = computed(() => {
  const list = rows.value.map((row, index) => ({ row, index }))
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  list.sort((a, b) => {
    const av = a.row[key]
    const bv = b.row[key]
    const an = av === null || av === undefined || Number.isNaN(av)
    const bn = bv === null || bv === undefined || Number.isNaN(bv)
    if (an && bn) return a.index - b.index
    if (an) return 1
    if (bn) return -1
    if (av === bv) return a.index - b.index
    return av > bv ? dir : -dir
  })
  return list.map((item) => item.row)
})

function toggle(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}
function name(row) {
  const text = lang.value === 'zhs'
    ? (row.name_zh || row.name || row.card_id)
    : (row.name_en || row.name || row.card_id)
  if (row.upgrade && text && !String(text).endsWith('+')) return text + '+'
  return text
}
function change(row) {
  if (row.change === 'add') return t('deck.impactAdd')
  if (row.change === 'remove') return t('deck.impactRemove')
  return row.change || ''
}
function effect(code) {
  if (code === 'helps') return t('deck.impactHelps')
  if (code === 'hurts') return t('deck.impactHurts')
  if (code === 'flat') return t('deck.impactFlat')
  return ''
}
function flag(row) {
  if (!row.noisy) return '—'
  if (row.noisy_reason === 'wilson_overlap') return t('deck.impactOverlap')
  return t('deck.impactTooSmall')
}
function pct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return (Number(value) * 100).toFixed(1) + '%'
}
function plain(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toFixed(1)
}
function signedPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Number(value) * 100
  return (n > 0 ? '+' : '') + n.toFixed(1) + '%'
}
function signedNum(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return (n > 0 ? '+' : '') + n.toFixed(2)
}

async function load() {
  const job = props.jobId
  const deck = props.deckId
  if (!job && !deck) return
  const url = job
    ? '/api/runs/' + encodeURIComponent(job) + '/card_impact'
    : '/api/decks/' + encodeURIComponent(deck) + '/card_impact'
  try {
    doc.value = await api.get(url)
    err.value = ''
  } catch (e) {
    err.value = e.message
  }
}
function live() {
  const status = doc.value.status
  return !status || status === 'running' || status === 'queued'
}
function arm() {
  if (timer) clearInterval(timer)
  timer = null
  if (!props.jobId && !props.deckId) return
  load()
  timer = setInterval(() => {
    if (!live()) {
      clearInterval(timer)
      timer = null
      return
    }
    load()
  }, 400)
}
watch(() => [props.jobId, props.deckId], arm, { immediate: true })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.scroll { overflow-x: auto; margin-top: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #2A2A2F; }
th button { all: unset; cursor: pointer; font-weight: 700; color: #E4DFD8; }
th button:hover { color: #F0A486; }
.effect { margin-left: 4px; color: #8A857E; font-size: 11px; }
.hint.warn { color: #E0A86C; }
</style>
