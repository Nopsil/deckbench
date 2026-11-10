<template>
  <div class="picker" :data-deck="scope === 'deck' ? 'encounters' : undefined" :data-nt="scope === 'nt' ? 'encounters' : undefined">
    <h3>{{ t(scope === 'nt' ? 'nt.encounters' : 'deck.encounters') }}</h3>
    <div class="hint">{{ t(scope === 'nt' ? 'nt.encHint' : 'deck.encHint') }}</div>

    <div v-if="gauntlets.length" class="gauntlets">
      <div class="label">{{ t('deck.gauntlets') }}</div>
      <div class="hint">{{ t('deck.gauntletHint') }}</div>
      <div class="row">
        <button v-for="g in gauntlets" :key="g.id" type="button" :data-gauntlet="g.id" @click="applyGauntlet(g)">
          {{ t('deck.gauntletRow', { act: g.act, room: roomName(g.room) }) }}
        </button>
      </div>
    </div>

    <label class="erow pin" data-encounter="DUMMY">
      <input type="checkbox" :checked="selected.has('DUMMY')" @change="toggle(probe, $event.target.checked)" />
      <span class="grow">
        <span class="nm">{{ label(probe) }}</span>
        <span class="meta">DUMMY</span>
      </span>
    </label>

    <div class="filters">
      <label class="search" data-enc-search>
        <span>{{ t('deck.encSearch') }}</span>
        <input :value="draft" type="search" @input="onSearch($event.target.value)" />
      </label>
      <label>
        <span>{{ t('deck.act') }}</span>
        <select :value="act" @change="setAct($event.target.value)">
          <option value="">{{ t('deck.any') }}</option>
          <option v-for="item in acts" :key="item" :value="String(item)">{{ t('deck.actOption', { act: item }) }}</option>
        </select>
      </label>
      <label>
        <span>{{ t('deck.room') }}</span>
        <select :value="room" @change="setRoom($event.target.value)">
          <option value="">{{ t('deck.any') }}</option>
          <option v-for="item in rooms" :key="item" :value="item">{{ roomName(item) }}</option>
        </select>
      </label>
    </div>

    <div v-if="err" class="hint warn">{{ err }}</div>
    <div v-else-if="loading" class="hint">{{ t('deck.encLoading') }}</div>
    <div v-else-if="!shown.length" class="hint">{{ t('deck.encEmpty') }}</div>
    <div v-else class="list">
      <label v-for="enc in shown" :key="enc.id" class="erow" :data-encounter="enc.id">
        <input type="checkbox" :checked="selected.has(enc.id)" @change="toggle(enc, $event.target.checked)" />
        <span class="grow">
          <span class="nm">{{ label(enc) }}</span>
          <span class="meta">{{ alt(enc) }} · {{ roomName(enc.room) }} · {{ t('deck.actOption', { act: enc.act }) }}</span>
        </span>
      </label>
    </div>
    <div class="pager">
      <span class="hint">{{ t('deck.range', { a: rangeStart, b: rangeEnd, n: total }) }}</span>
      <span class="row">
        <button type="button" data-enc-prev :disabled="offset <= 0" @click="page(-1)">{{ t('deck.prev') }}</button>
        <button type="button" data-enc-next :disabled="offset + limit >= total" @click="page(1)">{{ t('deck.next') }}</button>
      </span>
    </div>

    <div class="label">{{ t('deck.selected') }}</div>
    <div v-if="!(modelValue || []).length" class="hint">{{ t('deck.encEmpty') }}</div>
    <div v-for="row in modelValue" :key="row.id" class="erow picked" :data-selected="row.id">
      <span class="grow">
        <span class="nm">{{ label(row) }}</span>
        <span class="meta">{{ row.id }}</span>
      </span>
      <label class="fights">
        <span>{{ t('deck.fights') }}</span>
        <input :data-fights="row.id" type="number" min="1" max="100" :value="row.fights" @change="setFights(row.id, $event.target.value)" />
      </label>
    </div>
    <div class="hint" data-enc-total>{{ t('deck.totalFights', { n: totalFights }) }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { t, tr, lang } from '../i18n'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  scope: { type: String, default: 'deck' },
})
const emit = defineEmits(['update:modelValue'])

const ROOM_TR = { normal: 'Monster', elite: 'Elite', boss: 'Boss', probe: '探针' }
const draft = ref('')
const q = ref('')
const act = ref('')
const room = ref('')
const offset = ref(0)
const limit = 40
const total = ref(0)
const rows = ref([])
const acts = ref([])
const rooms = ref([])
const gauntlets = ref([])
const probeRow = ref(null)
const loading = ref(false)
const err = ref('')
let timer

const probe = computed(() => probeRow.value || {
  id: 'DUMMY', name: 'DUMMY', name_zh: '', name_en: '', act: null, room: 'probe',
})
const selected = computed(() => new Set((props.modelValue || []).map((row) => row.id)))
const shown = computed(() => rows.value.filter((row) => row.id !== 'DUMMY'))
const totalFights = computed(() => (props.modelValue || []).reduce((sum, row) => sum + (Number(row.fights) || 0), 0))
const rangeStart = computed(() => (total.value ? offset.value + 1 : 0))
const rangeEnd = computed(() => Math.min(offset.value + rows.value.length, total.value))

function roomName(value) {
  return tr('room.', ROOM_TR[value] || value)
}
function label(row) {
  if (!row) return ''
  if (row.id === 'DUMMY') return t('deck.dummyName')
  if (lang.value === 'zhs') return row.name_zh || row.name || row.id
  return row.name_en || row.name || row.id
}
function alt(row) {
  const primary = label(row)
  const other = lang.value === 'zhs' ? (row.name_en || '') : (row.name_zh || '')
  if (other && other !== primary) return other
  return row.id !== primary ? row.id : ''
}

async function load() {
  loading.value = true
  err.value = ''
  const params = new URLSearchParams({ offset: String(offset.value), limit: String(limit) })
  if (q.value) params.set('q', q.value)
  if (act.value) params.set('act', act.value)
  if (room.value) params.set('room', room.value)
  try {
    const data = await api.get('/api/encounters?' + params.toString())
    rows.value = data.encounters || []
    total.value = data.total || 0
    acts.value = data.acts || []
    rooms.value = data.rooms || []
    gauntlets.value = data.gauntlets || []
    if (data.probe) probeRow.value = data.probe
  } catch (e) {
    err.value = t('deck.encLoadFailed', { err: e.message })
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}
function reload() {
  offset.value = 0
  load()
}
function onSearch(value) {
  draft.value = value
  clearTimeout(timer)
  timer = setTimeout(() => { q.value = value.trim(); reload() }, 200)
}
function setAct(value) { act.value = value; reload() }
function setRoom(value) { room.value = value; reload() }
function page(dir) {
  offset.value = Math.max(0, offset.value + dir * limit)
  load()
}
function toggle(enc, on) {
  const cur = (props.modelValue || []).slice()
  const idx = cur.findIndex((row) => row.id === enc.id)
  if (on && idx < 0) cur.push({ ...enc, fights: 1 })
  if (!on && idx >= 0) cur.splice(idx, 1)
  emit('update:modelValue', cur)
}
function applyGauntlet(group) {
  emit('update:modelValue', (group.encounters || []).map((enc) => ({ ...enc, fights: 1 })))
}
function setFights(id, raw) {
  const n = Number.parseInt(raw, 10)
  const fights = Number.isFinite(n) ? Math.min(100, Math.max(1, n)) : 1
  emit('update:modelValue', (props.modelValue || []).map((row) => (row.id === id ? { ...row, fights } : row)))
}
onMounted(load)
</script>

<style scoped>
.picker { margin: 8px 0 4px; }
.gauntlets { margin: 10px 0; }
.row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.filters { display: grid; grid-template-columns: 1.4fr .8fr .8fr; gap: 8px; margin: 10px 0; }
.filters label, .fights { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #B9B4AC; }
.search { min-width: 0; }
.picker input:not([type="checkbox"]), .picker select {
  width: 100%; box-sizing: border-box; background: #1A1A1E; color: #EDE9E3;
  border: 1px solid #2E2E34; border-radius: 8px; padding: 6px 8px; font: inherit;
}
.picker input[type="checkbox"] { width: 16px; height: 16px; margin: 0; flex: none; }
.list { display: flex; flex-direction: column; gap: 6px; max-height: 240px; overflow: auto; }
.erow { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; background: #1A1A1E; border: 1px solid #2A2A2F; margin-top: 6px; }
.pin { margin-top: 10px; }
.grow { flex: 1; min-width: 0; }
.nm { display: block; font-weight: 600; font-size: 13.5px; }
.meta { display: block; color: #8A857E; font-size: 12px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker button { all: unset; cursor: pointer; padding: 4px 10px; border-radius: 8px; background: #2A2A30; color: #E4DFD8; font-size: 12.5px; font-weight: 650; }
.picker button:hover { background: rgba(217,119,87,.25); color: #F0A486; }
.picker button:disabled { opacity: .4; cursor: default; }
.pager { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.fights { width: 88px; flex: none; }
.fights input { text-align: right; }
.hint.warn { color: #E0A86C; }
@media (max-width: 720px) {
  .filters { grid-template-columns: 1fr; }
}
</style>
