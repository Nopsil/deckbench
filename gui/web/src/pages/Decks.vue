<template>
  <div class="page" data-page="decks">
    <div class="layout">
      <div class="pool">
        <div class="panel">
          <h3>{{ t('deck.pool') }}</h3>
          <div data-deck="search">
            <n-input :value="draft" clearable :placeholder="t('deck.searchPh')" @update:value="onSearch" />
          </div>
          <div class="filters">
            <label><span>{{ t('deck.character') }}</span>
              <n-select v-model:value="character" :options="opt(facets.characters)" size="small" @update:value="reload" /></label>
            <label><span>{{ t('deck.type') }}</span>
              <n-select v-model:value="cardType" :options="typeOptions" size="small" @update:value="reload" /></label>
            <label><span>{{ t('deck.cost') }}</span>
              <n-select v-model:value="cost" :options="costOptions" size="small" @update:value="reload" /></label>
            <label><span>{{ t('deck.rarity') }}</span>
              <n-select v-model:value="rarity" :options="rarityOptions" size="small" @update:value="reload" /></label>
          </div>
          <div v-if="err" class="hint warn">{{ err }}</div>
          <div v-else-if="loading" class="hint">{{ t('deck.loading') }}</div>
          <div v-else-if="!cards.length" class="hint">{{ t('deck.noMatch') }}</div>
          <div v-else class="cards">
            <div v-for="c in cards" :key="c.mod + ':' + c.id" class="crow" :data-card="c.mod + ':' + c.id">
              <div class="grow">
                <div class="nm">{{ label(c) }}</div>
                <div class="meta">{{ alt(c) }} · {{ tr('ctype.', c.type) }} · {{ tr('rarity.', c.rarity) }} · {{ costLabel(c.cost) }}</div>
              </div>
              <button type="button" class="add" data-add @click="add(c)">{{ t('deck.add') }}</button>
            </div>
          </div>
          <div class="pager">
            <span class="hint">{{ t('deck.range', { a: rangeStart, b: rangeEnd, n: total }) }}</span>
            <span class="row">
              <button type="button" data-prev :disabled="offset <= 0" @click="page(-1)">{{ t('deck.prev') }}</button>
              <button type="button" data-next :disabled="offset + limit >= total" @click="page(1)">{{ t('deck.next') }}</button>
            </span>
          </div>
        </div>
      </div>

      <div class="side">
        <div class="panel">
          <h3>{{ t('deck.size') }}</h3>
          <div class="size" data-deck="size">{{ size }}</div>
          <div class="label">{{ t('deck.curve') }}</div>
          <svg data-deck="curve" viewBox="0 0 280 128" role="img" :aria-label="t('deck.curve')">
            <g v-for="(bar, i) in curve" :key="bar.key">
              <rect :x="12 + i * 44" :y="96 - bar.h" width="28" :height="bar.h" rx="3" fill="#D97757" />
              <text :x="26 + i * 44" :y="90 - bar.h" text-anchor="middle" fill="#EDE9E3" font-size="11">{{ bar.n }}</text>
              <text :x="26 + i * 44" y="116" text-anchor="middle" fill="#8A857E" font-size="11">{{ bar.label }}</text>
            </g>
          </svg>
          <div class="label">{{ t('deck.split') }}</div>
          <svg data-deck="split" viewBox="0 0 280 18" role="img" :aria-label="t('deck.split')">
            <rect v-for="seg in splitSegs" :key="seg.key" :x="seg.x" y="1" :width="seg.w" height="16" :fill="seg.color" rx="2" />
          </svg>
          <div class="split">
            <span><i class="atk"></i>{{ t('deck.attack') }} {{ split.Attack }}</span>
            <span><i class="sk"></i>{{ t('deck.skill') }} {{ split.Skill }}</span>
            <span><i class="pw"></i>{{ t('deck.power') }} {{ split.Power }}</span>
            <span><i class="ot"></i>{{ t('deck.other') }} {{ split.Other }}</span>
          </div>
        </div>

        <div class="panel">
          <h3>{{ t('page.decks.title') }}</h3>
          <div v-if="!rows.length" class="hint">{{ t('deck.empty') }}</div>
          <div v-for="row in rows" :key="row.mod + ':' + row.id + (row.upgrade ? '+' : '')" class="drow" :data-deck-card="row.mod + ':' + row.id">
            <div class="grow">
              <div class="nm">{{ label(row) }}<span v-if="row.upgrade" class="up">+</span></div>
              <div class="meta">{{ alt(row) }} · {{ costLabel(row.upgrade ? row.cost_up : row.cost) }}</div>
            </div>
            <button type="button" data-dec @click="bump(row, -1)">-</button>
            <span data-count>{{ row.count }}</span>
            <button type="button" data-inc @click="bump(row, 1)">+</button>
            <button type="button" data-upgrade :class="{ on: row.upgrade }" :title="t('deck.upgrade')" @click="row.upgrade = !row.upgrade">+</button>
            <button type="button" data-remove :title="t('deck.remove')" @click="remove(row)">×</button>
          </div>
          <encounter-picker v-model="encounters" scope="deck" />
          <div class="field" data-deck="id"><div class="label">{{ t('deck.id') }}</div>
            <n-input v-model:value="deckId" maxlength="32" /></div>
          <div class="field" data-deck="name"><div class="label">{{ t('deck.name') }}</div>
            <n-input v-model:value="deckName" maxlength="80" /></div>
          <div class="field">
            <div class="label">{{ t('deck.maxTurns') }}</div>
            <input data-deck="turns" type="number" :min="1" :max="turnLimit" :value="maxTurns" @input="onTurns" />
            <div class="hint">{{ t('deck.maxTurnsHint') }}</div>
          </div>
          <div data-deck="save">
            <n-button type="primary" block :loading="saving" :disabled="!canSave" @click="save">{{ t('deck.save') }}</n-button>
          </div>
          <div v-if="savedId" class="hint ok" data-deck="saved">{{ t('deck.saved', { id: savedId }) }}</div>
          <div class="hint">{{ t('deck.runHint') }}</div>
          <div v-if="deckMod" class="hint">{{ t('deck.mod') }}: <span class="mono">{{ deckMod }}</span></div>
        </div>

        <div class="panel" data-deck="workers">
          <div class="label">{{ t('deck.workers') }} <b>{{ workers }}</b><span class="hint"> {{ t('nt.cores', { n: workerCap }) }}</span></div>
          <input data-deck="workers-range" type="range" :min="1" :max="workerCap" :value="workers" @input="onWorkers" />
          <div class="hint">{{ t('deck.workersHint') }}</div>
        </div>

        <div class="panel" data-deck="h2h">
          <h3>{{ t('deck.h2h') }}</h3>
          <div class="hint">{{ t('deck.h2hHint') }}</div>
          <div v-if="savedPresets.length < 2" class="hint">{{ t('deck.h2hNeed') }}</div>
          <div class="field" data-deck="h2h-a">
            <div class="label">A</div>
            <n-select v-model:value="h2hA" :options="presetOptions" :placeholder="t('deck.h2hPick')" />
          </div>
          <div class="field" data-deck="h2h-b">
            <div class="label">B</div>
            <n-select v-model:value="h2hB" :options="presetOptions" :placeholder="t('deck.h2hPick')" />
          </div>
          <label class="check">
            <input v-model="h2hOverride" data-deck="h2h-override" type="checkbox" />
            {{ t('deck.h2hOverride') }}
          </label>
          <div v-if="h2hErr" class="hint warn" data-deck="h2h-error">{{ h2hErr }}</div>
          <div data-deck="h2h-run">
            <n-button type="primary" block :loading="h2hRunning" :disabled="!canH2h" @click="runHeadToHead">{{ t('deck.h2hRun') }}</n-button>
          </div>
          <div v-if="h2hIds" data-h2h-progress>
            <div class="label">{{ t('deck.h2hProgress') }}</div>
            <run-progress :run-id="h2hIds.a" :cancellable="false" @update="(view) => onH2h('a', view)" />
            <run-progress :run-id="h2hIds.b" :cancellable="false" @update="(view) => onH2h('b', view)" />
            <n-button v-if="h2hActive" secondary type="error" block data-action="cancel" @click="cancelHeadToHead">{{ t('deck.h2hCancel') }}</n-button>
            <div v-if="h2hPartial" class="hint warn" data-partial>{{ t('run.partialHint') }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel impact" data-deck="impact">
      <h3>{{ t('deck.impact') }}</h3>
      <div class="hint">{{ t('deck.impactHint') }}</div>
      <div v-if="!savedPresets.length" class="hint">{{ t('deck.impactNeed') }}</div>
      <div class="impact-form">
        <div class="field" data-deck="impact-deck">
          <div class="label">{{ t('deck.impactPick') }}</div>
          <n-select v-model:value="impactDeck" :options="presetOptions" :placeholder="t('deck.impactPick')" />
        </div>
        <label class="check">
          <input v-model="impactPlus" data-deck="impact-plus" type="checkbox" />
          {{ t('deck.impactPlus') }}
        </label>
        <div data-deck="impact-run">
          <n-button type="primary" :loading="impactStarting" :disabled="!canImpact" @click="runImpact">{{ t('deck.impactRun') }}</n-button>
        </div>
      </div>
      <div v-if="impactErr" class="hint warn" data-deck="impact-error">{{ impactErr }}</div>
      <div v-if="impactJob" data-deck="impact-progress">
        <run-progress :run-id="impactJob" @update="onImpact" />
        <card-impact-table :job-id="impactJob" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NInput, NSelect, useMessage } from 'naive-ui'
import CardImpactTable from '../components/CardImpactTable.vue'
import EncounterPicker from '../components/EncounterPicker.vue'
import RunProgress from '../components/RunProgress.vue'
import { api, store } from '../api'
import { t, tr, lang } from '../i18n'

const msg = useMessage()
const router = useRouter()
const draft = ref('')
const q = ref('')
const character = ref('')
const cardType = ref('')
const cost = ref('')
const rarity = ref('')
const offset = ref(0)
const limit = 40
const total = ref(0)
const cards = ref([])
const facets = ref({ characters: [], types: [], rarities: [], costs: [] })
const loading = ref(false)
const err = ref('')
const rows = ref([])
const deckMod = ref('')
const deckId = ref('')
const deckName = ref('')
const encounters = ref([{ id: 'DUMMY', fights: 1 }])
const maxTurns = ref(1)
const fullTurns = ref(0)
const turnLimit = ref(200)
const turnsTouched = ref(false)
const turnsReady = ref(false)
const saving = ref(false)
const savedId = ref('')
const workers = ref(1)
const h2hA = ref(null)
const h2hB = ref(null)
const h2hOverride = ref(false)
const h2hRunning = ref(false)
const h2hErr = ref('')
const h2hIds = ref(null)
const h2hState = ref({ a: null, b: null })
const impactDeck = ref(null)
const impactPlus = ref(false)
const impactStarting = ref(false)
const impactErr = ref('')
const impactJob = ref('')
const impactState = ref(null)
let h2hLeft = false
let timer
function onlyDummy(list) {
  return (list || []).length > 0 && list.every((row) => row.id === 'DUMMY')
}
function applyTurnDefault() {
  if (turnsTouched.value || !fullTurns.value) return
  maxTurns.value = onlyDummy(encounters.value) ? 1 : fullTurns.value
}
watch(encounters, () => { savedId.value = ''; applyTurnDefault() }, { deep: true })
const workerCap = computed(() => Math.max(1, Math.min(Number((store.catalog && (store.catalog.worker_cap || store.catalog.cpu)) || 1), 8)))
function onWorkers(event) {
  const n = Number.parseInt(event.target.value, 10)
  workers.value = Math.max(1, Math.min(workerCap.value, Number.isFinite(n) ? n : 1))
}
function onTurns(event) {
  turnsTouched.value = true
  savedId.value = ''
  const n = Number.parseInt(event.target.value, 10)
  if (Number.isFinite(n)) maxTurns.value = n
}
async function loadTurnCap() {
  try {
    const data = await api.get('/api/encounters?limit=1')
    if (data.full_turns) fullTurns.value = data.full_turns
    if (data.turn_limit) turnLimit.value = data.turn_limit
    applyTurnDefault()
  } catch (e) { /* omitted max_turns still uses the server default */ }
  finally { turnsReady.value = true }
}

const any = () => ({ label: t('deck.any'), value: '' })
function opt(list) { return [any(), ...(list || []).map((v) => ({ label: v, value: v }))] }
const typeOptions = computed(() => [any(), ...(facets.value.types || []).map((v) => ({ label: tr('ctype.', v), value: v }))])
const rarityOptions = computed(() => [any(), ...(facets.value.rarities || []).map((v) => ({ label: tr('rarity.', v), value: v }))])
const costOptions = computed(() => [any(), ...(facets.value.costs || []).map((v) => ({ label: v === 'none' ? t('deck.unplayable') : v, value: v }))])

function label(c) {
  if (!c) return ''
  if (lang.value === 'zhs') return c.name_zh || c.name || c.id
  return c.name_en || c.name || c.id
}
function alt(c) {
  const primary = label(c)
  const other = lang.value === 'zhs' ? (c.name_en || '') : (c.name_zh || '')
  if (other && other !== primary) return other
  return c.id !== primary ? c.id : ''
}
function costLabel(costValue) {
  if (costValue === null || costValue === undefined) return t('deck.unplayable')
  if (costValue === 'X') return t('deck.xCost')
  return String(costValue)
}

async function load() {
  loading.value = true
  err.value = ''
  const params = new URLSearchParams({ offset: String(offset.value), limit: String(limit) })
  if (q.value) params.set('q', q.value)
  if (character.value) params.set('character', character.value)
  if (cardType.value) params.set('type', cardType.value)
  if (cost.value) params.set('cost', cost.value)
  if (rarity.value) params.set('rarity', rarity.value)
  try {
    const data = await api.get('/api/cards?' + params.toString())
    cards.value = data.cards || []
    total.value = data.total || 0
    facets.value = { characters: data.characters || [], types: data.types || [], rarities: data.rarities || [], costs: data.costs || [] }
  } catch (e) {
    err.value = t('deck.loadFailed', { err: e.message })
    cards.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}
function reload() { offset.value = 0; load() }
function onSearch(value) {
  draft.value = value
  clearTimeout(timer)
  timer = setTimeout(() => { q.value = value.trim(); reload() }, 200)
}
function page(dir) {
  offset.value = Math.max(0, offset.value + dir * limit)
  load()
}
const rangeStart = computed(() => (total.value ? offset.value + 1 : 0))
const rangeEnd = computed(() => Math.min(offset.value + cards.value.length, total.value))

function add(card) {
  if (card.mod !== 'builtin') {
    if (deckMod.value && deckMod.value !== card.mod) {
      msg.error(t('deck.oneMod'))
      return
    }
    deckMod.value = card.mod
  }
  const found = rows.value.find((row) => row.id === card.id && row.mod === card.mod && !row.upgrade)
  if (found) bump(found, 1)
  else rows.value.push({ ...card, count: 1, upgrade: false })
  savedId.value = ''
}
function bump(row, delta) {
  const next = row.count + delta
  if (next < 1 || next > 15) return
  row.count = next
  savedId.value = ''
}
function remove(row) {
  rows.value = rows.value.filter((item) => item !== row)
  if (!rows.value.some((item) => item.mod !== 'builtin')) deckMod.value = ''
  savedId.value = ''
}

const size = computed(() => rows.value.reduce((sum, row) => sum + row.count, 0))
const curve = computed(() => {
  const keys = ['0', '1', '2', '3', '4+', 'X']
  const counts = Object.fromEntries(keys.map((key) => [key, 0]))
  for (const row of rows.value) {
    const value = row.upgrade ? row.cost_up : row.cost
    let key = 'X'
    if (value === null || value === undefined) key = '4+'
    else if (value === 'X') key = 'X'
    else if (Number(value) >= 4) key = '4+'
    else key = String(value)
    counts[key] += row.count
  }
  const max = Math.max(1, ...Object.values(counts))
  return keys.map((key) => ({ key, label: key === '4+' ? '4+' : key, n: counts[key], h: Math.round(72 * counts[key] / max) || (counts[key] ? 4 : 0) }))
})
const split = computed(() => {
  const out = { Attack: 0, Skill: 0, Power: 0, Other: 0 }
  for (const row of rows.value) {
    const key = out[row.type] !== undefined ? row.type : 'Other'
    out[key] += row.count
  }
  return out
})
const splitSegs = computed(() => {
  const parts = [
    ['Attack', '#E07A5F'],
    ['Skill', '#7FA7C9'],
    ['Power', '#E3B47E'],
    ['Other', '#8A857E'],
  ]
  const totalN = Math.max(1, size.value)
  let x = 0
  return parts.map(([key, color]) => {
    const w = 280 * split.value[key] / totalN
    const seg = { key, color, x, w: Math.max(0, w - (w > 0 ? 2 : 0)) }
    x += w
    return seg
  }).filter((seg) => seg.w > 0)
})
const canSave = computed(() => /^[A-Za-z][A-Za-z0-9_]{0,31}$/.test(deckId.value.trim()) && deckName.value.trim() && rows.value.length > 0 && !!deckMod.value && encounters.value.length > 0 && !saving.value)
const savedPresets = computed(() => ((store.catalog && store.catalog.experiments) || []).filter((item) => item.user))
const presetOptions = computed(() => savedPresets.value.map((item) => ({
  label: `${item.title || item.name || item.id} (${item.id})`,
  value: item.id,
})))
const h2hActive = computed(() => {
  const a = h2hState.value.a
  const b = h2hState.value.b
  const live = (row) => row && (row.status === 'running' || row.status === 'queued')
  return !!(h2hIds.value && (live(a) || live(b) || !a || !b))
})
const h2hPartial = computed(() => {
  const a = h2hState.value.a
  const b = h2hState.value.b
  return !!((a && (a.partial || a.status === 'cancelled')) || (b && (b.partial || b.status === 'cancelled')))
})
const canH2h = computed(() => !!h2hA.value && !!h2hB.value && h2hA.value !== h2hB.value && !h2hRunning.value && !h2hActive.value)
const impactLive = computed(() => {
  const row = impactState.value
  return !!(impactJob.value && row && (row.status === 'running' || row.status === 'queued'))
})
const canImpact = computed(() => !!impactDeck.value && !impactStarting.value && !impactLive.value)

async function save() {
  if (!canSave.value) return
  saving.value = true
  savedId.value = ''
  try {
    const body = {
      id: deckId.value.trim(),
      name: deckName.value.trim(),
      mod: deckMod.value,
      cards: rows.value.map((row) => ({ id: row.id, count: row.count, upgrade: !!row.upgrade })),
      encounters: encounters.value.map((row) => ({ id: row.id, fights: Number(row.fights) || 1 })),
    }
    if (turnsTouched.value || (turnsReady.value && fullTurns.value)) body.max_turns = maxTurns.value
    const saved = await api.post('/api/decks', body)
    savedId.value = saved.id
    await store.loadCatalog()
    impactDeck.value = saved.id
  } catch (e) {
    msg.error(e.message)
  } finally {
    saving.value = false
  }
}
async function runHeadToHead() {
  if (!canH2h.value) return
  h2hRunning.value = true
  h2hErr.value = ''
  try {
    const body = { a: h2hA.value, b: h2hB.value, workers: workers.value }
    if (h2hOverride.value) {
      body.encounters = encounters.value.map((row) => ({ id: row.id, fights: Number(row.fights) || 1 }))
      body.max_turns = maxTurns.value
    }
    const saved = await api.post('/api/decks/head_to_head', body)
    h2hLeft = false
    h2hState.value = { a: null, b: null }
    h2hIds.value = { a: saved.a, b: saved.b }
    await store.loadRuns()
  } catch (e) {
    h2hErr.value = e.message
    msg.error(e.message)
  } finally {
    h2hRunning.value = false
  }
}
function onH2h(side, view) {
  h2hState.value = { ...h2hState.value, [side]: view }
  const a = h2hState.value.a
  const b = h2hState.value.b
  if (h2hLeft || !a || !b) return
  if ([a.status, b.status].some((status) => status === 'running' || status === 'queued')) return
  h2hLeft = true
  if (a.status === 'done' && b.status === 'done') {
    router.push({ path: '/compare', query: { a: a.id, b: b.id } })
  }
}
function onImpact(view) { impactState.value = view }
async function runImpact() {
  if (!canImpact.value) return
  impactStarting.value = true
  impactErr.value = ''
  try {
    const saved = await api.post('/api/decks/' + encodeURIComponent(impactDeck.value) + '/card_impact', {
      plus: impactPlus.value,
      workers: workers.value,
    })
    impactState.value = null
    impactJob.value = saved.id || saved.job
  } catch (e) {
    impactErr.value = e.message
  } finally {
    impactStarting.value = false
  }
}
async function cancelHeadToHead() {
  const ids = h2hIds.value
  if (!ids) return
  try {
    await api.post('/api/runs/' + encodeURIComponent(ids.a) + '/cancel')
    await api.post('/api/runs/' + encodeURIComponent(ids.b) + '/cancel')
  } catch (e) {
    h2hErr.value = e.message
    msg.error(e.message)
  }
}
onMounted(() => { load(); loadTurnCap(); store.loadCatalog() })
</script>

<style scoped>
.layout { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(300px, .8fr); gap: 16px; align-items: start; }
.filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.filters label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #B9B4AC; }
.cards { display: flex; flex-direction: column; gap: 8px; margin-top: 14px; max-height: 560px; overflow: auto; }
.crow, .drow { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; background: #1A1A1E; border: 1px solid #2A2A2F; }
.grow { flex: 1; min-width: 0; }
.nm { font-weight: 600; font-size: 14px; }
.meta { color: #8A857E; font-size: 12px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.add, .drow button, .pager button { all: unset; cursor: pointer; padding: 4px 10px; border-radius: 8px; background: #2A2A30; color: #E4DFD8; font-size: 12.5px; font-weight: 650; }
.add:hover, .drow button:hover, .pager button:hover { background: rgba(217,119,87,.25); color: #F0A486; }
.pager button:disabled { opacity: .4; cursor: default; }
.pager { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
.side { display: flex; flex-direction: column; gap: 16px; }
.size { font-size: 36px; font-weight: 700; color: #F0A486; line-height: 1; margin: 4px 0 12px; }
svg { width: 100%; height: auto; display: block; margin: 4px 0 10px; }
.split { display: flex; flex-wrap: wrap; gap: 8px 12px; font-size: 12px; color: #B9B4AC; }
.split i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; }
.atk { background: #E07A5F; } .sk { background: #7FA7C9; } .pw { background: #E3B47E; } .ot { background: #8A857E; }
.drow { margin-bottom: 8px; }
.drow button { padding: 2px 8px; }
.drow [data-upgrade].on { background: rgba(217,119,87,.3); color: #F0A486; }
.up { color: #F0A486; margin-left: 4px; }
.field { margin: 10px 0; }
.field input[type="number"] { width: 100%; box-sizing: border-box; background: #1A1A1E; color: #EDE9E3; border: 1px solid #2E2E34; border-radius: 8px; padding: 6px 8px; font: inherit; }
.hint.warn { color: #E0A86C; }
.impact { margin-top: 16px; }
.impact-form { display: grid; grid-template-columns: minmax(220px, 360px) auto auto; gap: 12px 16px; align-items: end; }
.impact-form .check { margin: 0 0 8px; }
.hint.ok { color: #8FBF8F; }
.check { display: flex; gap: 8px; align-items: flex-start; margin: 8px 0 12px; font-size: 13px; color: #B9B4AC; }
.check input { margin-top: 2px; }
@media (max-width: 980px) {
  .layout { grid-template-columns: 1fr; }
  .filters { grid-template-columns: 1fr 1fr; }
  .impact-form { grid-template-columns: 1fr; }
}
</style>
