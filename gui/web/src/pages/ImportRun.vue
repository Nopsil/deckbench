<template>
  <div class="page">
    <div class="panel">
      <p class="hint" style="margin-top:0">{{ t('imp.readonly') }}</p>
      <div class="label">{{ t('imp.hint') }}</div>
      <div class="row tools" style="align-items:stretch">
        <n-input v-model:value="path" :placeholder="t('imp.pathPh')" :disabled="loading" @keyup.enter="readPath" />
        <n-button type="primary" :loading="loading" @click="readPath">{{ t('imp.read') }}</n-button>
        <n-button secondary :disabled="loading" @click="pickFile">
          <template #icon><n-icon :component="FileImport" /></template>{{ t('imp.upload') }}
        </n-button>
        <input ref="fileEl" type="file" class="file" @change="onFile" />
      </div>
      <p class="hint">{{ t('imp.locations') }}</p>
      <div v-if="folders.length" class="suggest">
        <div class="sec-title">{{ t('imp.suggest') }}</div>
        <div class="row" style="flex-wrap:wrap">
          <button v-for="f in folders" :key="f.path" type="button" class="chip link" @click="readPath(f.path)">
            <n-icon :component="Folder" size="14" /> {{ f.label }}
          </button>
        </div>
      </div>
      <p v-else class="hint">{{ t('imp.noSuggest') }}</p>
    </div>

    <div v-if="loading" class="panel" style="text-align:center"><n-spin size="small" /> <span class="muted">{{ t('imp.loading') }}</span></div>

    <div v-else-if="index" class="panel">
      <div class="row between">
        <h3 style="margin:0">{{ t('imp.pick') }}</h3>
        <span class="faint">{{ index.root }}</span>
      </div>
      <p v-if="indexWarn" class="hint">{{ indexWarn }}</p>
      <div v-if="!index.runs.length" class="empty"><div class="big">{{ t('imp.emptyDir') }}</div></div>
      <table v-else class="runs">
        <thead>
          <tr>
            <th>{{ t('imp.colFile') }}</th>
            <th>{{ t('imp.colSeed') }}</th>
            <th>{{ t('imp.colWho') }}</th>
            <th>{{ t('imp.colAsc') }}</th>
            <th>{{ t('imp.colFloors') }}</th>
            <th>{{ t('imp.colResult') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in index.runs" :key="r.path || r.filename" :class="{ bad: r.error, go: !r.error }" @click="openOne(r)">
            <td class="mono">{{ r.filename }}</td>
            <template v-if="r.error">
              <td colspan="5" class="err">{{ t('imp.unreadable', { name: r.filename }) }} {{ errText(r.error, r.error_info) }}</td>
            </template>
            <template v-else>
              <td class="mono">{{ r.seed || '—' }}</td>
              <td>{{ whoLabel(r.players && r.players[0], 0) }}</td>
              <td>{{ r.ascension ?? '—' }}</td>
              <td>{{ r.floors ?? '—' }}</td>
              <td>{{ resultName(r.result) }}</td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>

    <template v-else-if="run">
      <div class="row between" style="margin:4px 0 12px">
        <div class="row" style="flex-wrap:wrap">
          <n-button v-if="indexBackup" size="small" secondary @click="back">
            <template #icon><n-icon :component="ArrowLeft" /></template>{{ t('imp.back') }}
          </n-button>
          <span class="chip">{{ kindName(run.kind) }}</span>
          <span v-if="run.source && run.source.filename" class="chip mono">{{ run.source.filename }}</span>
          <span v-if="run.schema_version != null" class="chip">{{ t('imp.schema', { n: run.schema_version }) }}</span>
          <span v-if="run.build_id" class="chip">{{ t('imp.build', { id: run.build_id }) }}</span>
        </div>
        <n-select v-if="run.players.length > 1" v-model:value="player" :options="playerOptions" size="small" style="width:240px" />
      </div>
      <p v-if="run.players.length > 1" class="hint">{{ t('imp.coop', { n: run.players.length }) }}</p>

      <div class="grid g4 stats" style="margin-bottom:16px">
        <div class="stat hl">
          <div class="k">{{ t('imp.seed') }}</div>
          <div class="v mono seed">{{ run.seed || '—' }}</div>
          <div class="s">
            <span v-if="run.seed_canonical && run.seed_canonical !== run.seed">{{ t('imp.canonical') }} {{ run.seed_canonical }}</span>
            <n-button v-if="run.seed" text size="tiny" @click="copySeed">{{ t('imp.copy') }}</n-button>
          </div>
        </div>
        <div class="stat">
          <div class="k">{{ t('imp.character') }}</div>
          <div class="v">{{ whoLabel(who, player) }}</div>
          <div class="s">{{ who && who.id ? who.id : '' }}</div>
        </div>
        <div class="stat">
          <div class="k">{{ t('imp.result') }}</div>
          <div class="v">{{ resultName(run.result) }}</div>
          <div class="s">{{ t('imp.ascension') }} {{ run.ascension ?? '—' }}<span v-if="run.game_mode"> · {{ run.game_mode }}</span></div>
        </div>
        <div class="stat">
          <div class="k">{{ t('imp.floors') }}</div>
          <div class="v">{{ run.route.length }}</div>
          <div class="s">
            <span v-if="run.start_time">{{ t('imp.started') }} {{ when(run.start_time) }}</span>
            <span v-if="run.killed_by"> · {{ t('imp.killedBy') }} {{ modelLabel(run.killed_by) }}</span>
          </div>
        </div>
      </div>

      <div v-if="run.warnings.length" class="panel" style="padding:12px 16px">
        <div v-for="(w, i) in run.warnings" :key="i" class="hint" style="margin:0">{{ warnText(w) }}</div>
      </div>

      <div v-if="run.modifiers && run.modifiers.length" class="row" style="flex-wrap:wrap; margin-bottom:12px">
        <span class="faint">{{ t('imp.modifiers') }}</span>
        <span v-for="m in run.modifiers" :key="m.id" class="chip">{{ m.name || m.id }}</span>
      </div>

      <div v-for="m in run.maps" :key="'map'+m.act" class="panel">
        <h3>{{ t('imp.openMap') }} · {{ t('imp.act', { n: m.act + 1 }) }} <span class="faint">{{ m.act_id }}</span></h3>
        <p class="hint">{{ t('imp.mapNote') }}</p>
        <svg v-if="mapBox(m)" :width="mapBox(m).w" :height="mapBox(m).h" class="mapsvg">
          <line v-for="(ln, i) in mapBox(m).lines" :key="'l'+m.act+'-'+i" :x1="ln.x1" :y1="ln.y1" :x2="ln.x2" :y2="ln.y2" />
          <g v-for="(n, i) in mapBox(m).nodes" :key="'n'+m.act+'-'+i">
            <rect :x="n.x - 12" :y="n.y - 12" width="24" height="24" rx="6" :class="{ on: n.visited }" />
            <text :x="n.x" :y="n.y + 4">{{ pointLetter(n.type) }}</text>
            <title>{{ pointName(n.type) }} {{ t('imp.coord', { col: n.col, row: n.row }) }}</title>
          </g>
        </svg>
      </div>

      <div class="layout">
        <div>
          <div class="sec-title">{{ t('imp.route') }}</div>
          <div v-if="!run.route.length" class="panel"><div class="empty"><div class="big">{{ t('imp.noRoute') }}</div></div></div>
          <div v-for="step in run.route" :key="step.floor" class="panel step">
            <div class="row between">
              <div class="row" style="flex-wrap:wrap">
                <span class="chip acc">{{ t('imp.floor', { n: step.floor }) }}</span>
                <span class="chip">{{ t('imp.act', { n: step.act + 1 }) }}</span>
                <span class="chip">{{ pointName(step.type) }}</span>
                <span v-if="step.coord" class="chip mono">{{ t('imp.coord', { col: step.coord.col, row: step.coord.row }) }}</span>
              </div>
              <span v-if="statsFor(step) && statsFor(step).hp != null" class="faint">
                {{ t('imp.hp', { cur: statsFor(step).hp, mx: statsFor(step).max_hp ?? '—' }) }}
                <span v-if="statsFor(step).gold != null"> · {{ t('imp.gold', { n: statsFor(step).gold }) }}</span>
              </span>
            </div>
            <div v-if="step.rooms.length" class="rooms">
              <div v-for="(room, i) in step.rooms" :key="i">
                <span class="mono">{{ room.name || room.id || pointName(room.type) }}</span>
                <span v-if="room.monsters.length" class="faint"> · {{ t('imp.monsters') }} {{ room.monsters.join(', ') }}</span>
              </div>
            </div>
            <template v-if="statsFor(step)">
              <div v-if="statsFor(step).card_choices.length" class="block">
                <div class="sec-title">{{ t('imp.picks') }}</div>
                <div class="row" style="flex-wrap:wrap">
                  <span v-for="(c, i) in statsFor(step).card_choices" :key="'c'+i" class="chip" :class="{ acc: c.picked }" :title="c.picked ? t('imp.picked') : t('imp.skipped')">{{ cardLabel(c) }}</span>
                </div>
              </div>
              <div v-if="statsFor(step).relic_choices.length" class="block">
                <div class="sec-title">{{ t('imp.relics') }}</div>
                <div class="row" style="flex-wrap:wrap">
                  <span v-for="(c, i) in statsFor(step).relic_choices" :key="'r'+i" class="chip" :class="{ acc: c.picked }">{{ c.name || c.id }}</span>
                </div>
              </div>
              <div v-if="statsFor(step).ancient.length" class="block">
                <div class="sec-title">{{ t('imp.ancient') }}</div>
                <div class="row" style="flex-wrap:wrap">
                  <span v-for="(c, i) in statsFor(step).ancient" :key="'a'+i" class="chip" :class="{ acc: c.picked }" :title="c.inferred ? t('imp.inferred') : ''">{{ c.name || c.id }}</span>
                </div>
              </div>
              <div v-if="extraLine(statsFor(step))" class="hint">{{ extraLine(statsFor(step)) }}</div>
            </template>
          </div>
          <p v-if="run.route.length && !anyPicks" class="hint">{{ t('imp.noPicks') }}</p>
        </div>
        <div>
          <div class="panel">
            <h3>{{ t('imp.relics') }}</h3>
            <div v-if="!who || !who.relics.length" class="faint">{{ t('imp.noRelics') }}</div>
            <div v-for="(r, i) in (who ? who.relics : [])" :key="'rel'+i" class="rel">
              <span>{{ r.name || r.id }}</span>
              <span v-if="r.floor != null" class="faint">{{ t('imp.floor', { n: r.floor }) }}</span>
            </div>
          </div>
          <div class="panel">
            <h3>{{ t('imp.deck') }}</h3>
            <div v-if="!who || !who.deck.length" class="faint">{{ t('imp.noDeck') }}</div>
            <div class="row" style="flex-wrap:wrap">
              <span v-for="(c, i) in (who ? who.deck : [])" :key="'d'+i" class="chip">{{ cardLabel(c) }}</span>
            </div>
          </div>
          <div v-if="who && who.potions.length" class="panel">
            <h3>{{ t('imp.potions') }}</h3>
            <div class="row" style="flex-wrap:wrap">
              <span v-for="(p, i) in who.potions" :key="'p'+i" class="chip">{{ p.name || p.id }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { NButton, NIcon, NInput, NSelect, NSpin, useMessage } from 'naive-ui'
import { ArrowLeft, FileImport, Folder } from '@vicons/tabler'
import { api } from '../api'
import { intlLocale, t } from '../i18n'

const msg = useMessage()
const path = ref('')
const loading = ref(false)
const folders = ref([])
const index = ref(null)
const indexBackup = ref(null)
const run = ref(null)
const player = ref(0)
const fileEl = ref(null)

const who = computed(() => (run.value && run.value.players[player.value]) || null)
const playerOptions = computed(() => (run.value ? run.value.players.map((p, i) => ({ label: whoLabel(p, i), value: i })) : []))
const indexWarn = computed(() => (index.value && index.value.warnings || []).map(warnText).join(' '))
const anyPicks = computed(() => {
  if (!run.value) return false
  return run.value.route.some((step) => {
    const st = statsFor(step)
    return st && (st.card_choices.length || st.relic_choices.length || st.ancient.length)
  })
})

function named(key, fallback) {
  const s = t(key)
  return s === key ? fallback : s
}
function pointName(type) { return named('imp.point.' + (type || 'unknown'), type || t('imp.point.unknown')) }
function pointLetter(type) { return named('imp.letter.' + (type || 'unknown'), '?') }
function resultName(r) { return named('imp.result.' + (r || 'unknown'), r || t('imp.result.unknown')) }
function kindName(k) { return named('imp.kind.' + k, k || '') }
function warnText(w) {
  const s = t('imp.warn.' + w.code, w)
  return s === 'imp.warn.' + w.code ? w.code : s
}
function errText(code, info) { return t('imp.err.' + code, info || {}) }
function whoLabel(p, i) {
  if (!p) return '—'
  return p.character_name || p.character || (i == null ? '—' : t('imp.player', { n: i + 1 }))
}
function modelLabel(id) { return id || '' }
function cardLabel(c) {
  if (!c) return ''
  const name = c.name || c.id || ''
  return c.upgrade ? name + ' ' + t('imp.upgrade', { n: c.upgrade }) : name
}
function statsFor(step) {
  const ps = step.players || []
  const id = who.value && who.value.id
  if (id != null && id !== '') {
    return ps.find((p) => p.id === id) || null
  }
  return ps[player.value] || null
}
function extraLine(st) {
  const bits = []
  const ids = (list) => (list || []).map((x) => (x && x.name) || (x && x.id) || x).filter(Boolean)
  if (st.cards_removed && st.cards_removed.length) bits.push(t('imp.removed') + ' ' + ids(st.cards_removed).join(', '))
  if (st.upgraded && st.upgraded.length) bits.push(t('imp.upgraded') + ' ' + st.upgraded.join(', '))
  if (st.bought_relics && st.bought_relics.length) bits.push(t('imp.bought') + ' ' + st.bought_relics.join(', '))
  if (st.bought_cards && st.bought_cards.length) bits.push(t('imp.bought') + ' ' + st.bought_cards.join(', '))
  if (st.rest && st.rest.length) bits.push(t('imp.rest') + ' ' + st.rest.join(', '))
  return bits.join(' · ')
}
function when(ts) {
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return ''
  return new Intl.DateTimeFormat(intlLocale(), { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(d)
}
function mapBox(m) {
  const pts = m.points || []
  if (!pts.length) return null
  const maxC = Math.max(...pts.map((p) => p.col))
  const minC = Math.min(...pts.map((p) => p.col))
  const maxR = Math.max(...pts.map((p) => p.row))
  const minR = Math.min(...pts.map((p) => p.row))
  const CW = 36, CH = 34, pad = 16
  const w = (maxC - minC + 1) * CW + pad * 2
  const h = (maxR - minR + 1) * CH + pad * 2
  const X = (c) => pad + (c - minC) * CW + CW / 2
  const Y = (r) => pad + (maxR - r) * CH + CH / 2
  const lines = []
  for (const p of pts) for (const ch of p.children || []) lines.push({ x1: X(p.col), y1: Y(p.row), x2: X(ch.col), y2: Y(ch.row) })
  return { w, h, lines, nodes: pts.map((p) => ({ ...p, x: X(p.col), y: Y(p.row) })) }
}
function show(data) {
  if (!data) return
  if (data.type === 'index') {
    index.value = data
    indexBackup.value = null
    run.value = null
    return
  }
  run.value = data.run
  player.value = 0
  index.value = null
}
async function readPath(explicit) {
  const p = typeof explicit === 'string' ? explicit : path.value.trim()
  if (typeof explicit === 'string') path.value = explicit
  if (!p) { msg.error(t('imp.err.not_found', { path: '' })); return }
  loading.value = true
  try {
    show(await api.post('/api/saves/open', { path: p }))
  } catch (e) { msg.error(e.message) }
  finally { loading.value = false }
}
function pickFile() { fileEl.value && fileEl.value.click() }
async function onFile(ev) {
  const f = ev.target.files && ev.target.files[0]
  ev.target.value = ''
  if (!f) return
  const body = new FormData()
  body.append('file', f)
  loading.value = true
  try {
    indexBackup.value = null
    show(await api.upload('/api/saves/upload', body))
  } catch (e) { msg.error(e.message) }
  finally { loading.value = false }
}
async function openOne(r) {
  if (r.error || !r.path) return
  const keep = index.value
  loading.value = true
  try {
    const data = await api.post('/api/saves/open', { path: r.path })
    show(data)
    if (data.type === 'run') indexBackup.value = keep
  } catch (e) { msg.error(e.message) }
  finally { loading.value = false }
}
function back() {
  index.value = indexBackup.value
  indexBackup.value = null
  run.value = null
}
async function copySeed() {
  const s = run.value && (run.value.seed_canonical || run.value.seed)
  if (!s) return
  try {
    await navigator.clipboard.writeText(s)
    msg.success(t('imp.copied'))
  } catch (e) { msg.info(s) }
}
onMounted(async () => {
  try { folders.value = (await api.get('/api/saves/suggest')).folders || [] } catch (e) { folders.value = [] }
})
</script>

<style scoped>
.file { display: none; }
.tools { flex-wrap: wrap; }
.tools :deep(.n-input) { flex: 1 1 240px; min-width: 0; }
.seed { font-size: 22px; word-break: break-all; }
.suggest { margin-top: 12px; }
.chip.link { cursor: pointer; font: inherit; color: inherit; }
.chip.link:hover { border-color: #D97757; }
.runs { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13.5px; }
.runs th { text-align: left; color: #9C978F; font-weight: 600; padding: 8px 10px; border-bottom: 1px solid #2E2E34; }
.runs td { padding: 8px 10px; border-bottom: 1px solid #26262B; }
.runs tr.go { cursor: pointer; }
.runs tr.go:hover td { background: #26262B; }
.runs td.err { color: #E06C6C; }
.layout { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(260px, 0.8fr); gap: 16px; align-items: start; }
.step { margin-bottom: 12px; }
.rooms { margin-top: 8px; font-size: 13px; }
.block { margin-top: 10px; }
.rel { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid #2A2A2F; font-size: 13.5px; }
.mapsvg { display: block; max-width: 100%; background: #18181B; border-radius: 12px; border: 1px solid #2E2E34; }
.mapsvg line { stroke: #3A3A41; stroke-width: 2; }
.mapsvg rect { fill: #26262B; stroke: #3A3A41; }
.mapsvg rect.on { fill: rgba(217, 119, 87, .28); stroke: #D97757; }
.mapsvg text { fill: #EDE9E3; font-size: 11px; text-anchor: middle; font-weight: 700; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .stats { grid-template-columns: 1fr 1fr; }
}
</style>
