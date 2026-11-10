<template>
  <div class="page">
    <div class="panel">
      <div class="label">{{ t('exp.path') }}</div>
      <div class="row">
        <n-input v-model:value="path" :placeholder="t('exp.pathPh')" style="flex:1" @keyup.enter="openLog" />
        <n-button type="primary" :loading="loading" @click="openLog">{{ t('exp.load') }}</n-button>
        <n-button secondary :loading="finding" @click="find">{{ t('exp.discover') }}</n-button>
      </div>
      <div class="hint">{{ t('exp.readOnly') }}</div>
      <div v-if="discoverError" class="hint warn">{{ discoverError }}</div>
      <div v-if="logs.length" class="roots">
        <div class="label">{{ t('exp.logs') }}</div>
        <button v-for="item in logs" :key="item.path" class="root" @click="pickLog(item.path)">
          <span class="mono">{{ item.path }}</span>
        </button>
        <div v-if="truncated" class="hint">{{ t('exp.truncated', { n: logs.length }) }}</div>
      </div>
      <div v-else-if="foundOnce && !logs.length" class="hint">{{ t('exp.discoverEmpty') }}</div>
    </div>

    <div v-if="error" class="panel state">
      <div class="big">{{ t('exp.errTitle') }}</div>
      <div class="detail">{{ error }}</div>
      <div class="hint">{{ t('exp.errHint') }}</div>
    </div>
    <div v-else-if="loading" class="panel state"><n-spin /><div class="hint">{{ t('exp.loading') }}</div></div>

    <template v-else-if="catalog">
      <div class="panel">
        <div class="hint mono">{{ catalog.path }}</div>
        <div class="grid g2 picks">
          <div>
            <div class="label">{{ t('exp.seed') }}</div>
            <n-select :value="seed" :options="seedOptions" @update:value="pickSeed" />
          </div>
          <div>
            <div class="label">{{ t('exp.fight') }}</div>
            <n-select :value="fight" :options="fightOptions" :disabled="!fightOptions.length" @update:value="pickFight" />
          </div>
        </div>
      </div>

      <div v-if="pageError" class="panel state">
        <div class="big">{{ t('exp.errTitle') }}</div>
        <div class="detail">{{ pageError }}</div>
      </div>
      <div v-else-if="!fights.length" class="panel state">
        <div class="big">{{ t('exp.noFights') }}</div>
      </div>
      <div v-else-if="paging" class="panel state"><n-spin /><div class="hint">{{ t('exp.loading') }}</div></div>
      <template v-else-if="pageDoc">
        <div class="panel">
          <div class="between head">
            <div>
              <h3>{{ whereText(pageDoc.where) || t('exp.fightN', { n: pageDoc.fight + 1 }) }}</h3>
              <div class="hint">{{ t('exp.closeHint', { gap: fmtScore(pageDoc.close_gap) }) }}</div>
            </div>
            <div class="hint">{{ t('exp.closeCount', { n: closeCount }) }}</div>
          </div>

          <article v-for="(d, i) in pageDoc.decisions" :key="(d.seq || i) + ':' + d.kind" class="decision" :class="{ close: d.close }" :data-close="d.close ? '1' : '0'">
            <div class="dh">
              <span class="kind">{{ kindText(d.kind) }}</span>
              <span v-if="d.turn != null" class="turn">{{ t('exp.turnN', { n: d.turn }) }}</span>
              <span v-if="d.floor != null" class="turn">{{ t('exp.floorN', { n: d.floor }) }}</span>
              <span v-if="d.close" class="badge close">{{ t('exp.close') }}</span>
            </div>
            <div class="chosen">
              <span class="k">{{ t('exp.chosen') }}</span>
              <span class="mono">{{ chosenText(d.chosen, d) }}</span>
            </div>
            <div v-if="d.card" class="hint">{{ t('exp.card', { card: d.card }) }}</div>
            <div class="margin" :class="{ close: d.close }">{{ marginText(d) }}</div>
            <div v-if="d.threshold != null" class="hint">{{ t('exp.threshold', { n: fmtScore(d.threshold) }) }}</div>
            <div v-if="d.note" class="hint">{{ d.note }}</div>
            <table class="cands">
              <thead>
                <tr>
                  <th>{{ t('exp.candidates') }}</th>
                  <th>{{ t('exp.target') }}</th>
                  <th>{{ t('exp.score') }}</th>
                  <th>{{ t('exp.note') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!(d.candidates || []).length">
                  <td colspan="4" class="faint">{{ t('common.none') }}</td>
                </tr>
                <tr v-for="(c, j) in d.candidates || []" :key="j" :class="{ picked: c.picked }">
                  <td class="mono">{{ c.name || c.id || t('common.none') }}<span v-if="c.picked" class="pick">{{ t('exp.picked') }}</span></td>
                  <td class="mono">{{ c.target || t('common.none') }}</td>
                  <td class="mono">{{ c.score == null ? t('common.none') : fmtScore(c.score) }}</td>
                  <td class="mono mech">{{ c.note || t('common.none') }}</td>
                </tr>
              </tbody>
            </table>
          </article>

          <div class="pager">
            <n-button secondary :disabled="pageDoc.offset === 0" @click="prevPage">{{ t('exp.prev') }}</n-button>
            <span class="hint">{{ t('exp.page', { start: pageStart, end: pageEnd, total: pageDoc.total }) }}</span>
            <n-button secondary :disabled="pageDoc.next_offset == null" @click="nextPage">{{ t('exp.next') }}</n-button>
          </div>
        </div>
      </template>
    </template>

    <div v-else class="panel state">
      <div class="big">{{ t('exp.emptyTitle') }}</div>
      <div class="detail">{{ t('exp.emptyHint') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NInput, NSelect, NSpin, useMessage } from 'naive-ui'
import { api } from '../api'
import { t } from '../i18n'

const route = useRoute()
const msg = useMessage()
const PAGE = 20

function qstr(v) {
  if (Array.isArray(v)) v = v[0]
  return v == null ? '' : String(v)
}
function intQuery(v) {
  const s = qstr(v)
  if (!/^\d+$/.test(s)) return 0
  return Number(s)
}
function fmtScore(n) {
  if (n == null || Number.isNaN(Number(n))) return t('common.none')
  return Number(n).toFixed(4).replace(/\.?0+$/, '')
}

const path = ref(qstr(route.query.path))
const seed = ref(qstr(route.query.seed))
const fight = ref(intQuery(route.query.fight))
const offset = ref(0)
const catalog = ref(null)
const pageDoc = ref(null)
const logs = ref([])
const truncated = ref(false)
const foundOnce = ref(false)
const error = ref('')
const pageError = ref('')
const discoverError = ref('')
const loading = ref(false)
const finding = ref(false)
const paging = ref(false)

const runs = computed(() => (catalog.value && catalog.value.runs) || [])
const run = computed(() => runs.value.find((r) => (r.seed || '') === seed.value) || null)
const fights = computed(() => (run.value && run.value.fights) || [])
const seedOptions = computed(() => runs.value.map((r) => ({ label: runLabel(r), value: r.seed || '' })))
const fightOptions = computed(() => fights.value.map((f) => ({ label: fightLabel(f), value: f.fight })))
const closeCount = computed(() => ((pageDoc.value && pageDoc.value.decisions) || []).filter((d) => d.close).length)
const pageStart = computed(() => (pageDoc.value && pageDoc.value.total ? pageDoc.value.offset + 1 : 0))
const pageEnd = computed(() => (pageDoc.value ? pageDoc.value.offset + (pageDoc.value.decisions || []).length : 0))

function runLabel(r) {
  const who = r.seed || t('exp.noSeed')
  const bits = [who]
  if (r.char) bits.push(r.char)
  bits.push(t('exp.nFights', { n: (r.fights || []).length }))
  return bits.join(' · ')
}
function fightLabel(f) {
  const w = f.where || {}
  const bits = [t('exp.fightN', { n: f.fight + 1 })]
  if (w.floor != null) bits.push(t('exp.floorN', { n: w.floor }))
  if (w.encounter) bits.push(String(w.encounter))
  else if (w.room) bits.push(String(w.room))
  bits.push(t('exp.nDecisions', { n: f.decisions }))
  return bits.join(' · ')
}
function whereText(w) {
  if (!w) return ''
  const bits = []
  if (w.seed) bits.push(String(w.seed))
  if (w.char) bits.push(String(w.char))
  if (w.act != null) bits.push(t('exp.actN', { n: w.act }))
  if (w.floor != null) bits.push(t('exp.floorN', { n: w.floor }))
  if (w.room) bits.push(String(w.room))
  if (w.encounter) bits.push(String(w.encounter))
  return bits.join(' · ')
}
function kindText(k) {
  if (k === 'play') return t('exp.kind.play')
  if (k === 'target') return t('exp.kind.target')
  if (k === 'potion') return t('exp.kind.potion')
  if (k === 'reward') return t('exp.kind.reward')
  if (k === 'shop') return t('exp.kind.shop')
  return k || ''
}
function oneChoice(c, fallbackNote) {
  if (!c || typeof c !== 'object') return t('common.none')
  const bits = [c.name || c.id || t('common.none')]
  if (c.target) bits.push(String(c.target))
  if (c.score != null) bits.push(fmtScore(c.score))
  const note = c.note || fallbackNote
  if (note) bits.push(String(note))
  return bits.join(' ')
}
function chosenText(ch, decision) {
  const picked = ((decision && decision.candidates) || []).find((c) => c && c.picked)
  const fallback = picked && picked.note ? picked.note : ''
  if (ch == null) return fallback || t('common.none')
  if (Array.isArray(ch)) {
    if (!ch.length) return fallback || t('common.none')
    return ch.map((c) => oneChoice(c, '')).join(t('sep.list'))
  }
  return oneChoice(ch, fallback)
}
function marginText(d) {
  const who = d.runner_up ? (d.runner_up.name || d.runner_up.id || t('common.none')) : ''
  if (d.margin == null) return d.runner_up ? t('exp.noScore') : t('exp.noRunner')
  if (d.margin === 0) return t('exp.tie', { who })
  if (d.margin > 0) return t('exp.ahead', { n: fmtScore(d.margin), who })
  return t('exp.behind', { n: fmtScore(-d.margin), who })
}

function alignSelection() {
  if (!runs.value.length) {
    seed.value = ''
    fight.value = 0
    return
  }
  if (!runs.value.some((r) => (r.seed || '') === seed.value)) seed.value = runs.value[0].seed || ''
  if (!fights.value.some((f) => f.fight === fight.value)) fight.value = fights.value.length ? fights.value[0].fight : 0
}

async function loadPage() {
  pageError.value = ''
  if (!catalog.value || !path.value.trim() || !fights.value.length) {
    pageDoc.value = null
    return
  }
  paging.value = true
  try {
    pageDoc.value = await api.post('/api/explain/fight', {
      path: path.value.trim(),
      seed: seed.value,
      fight: fight.value,
      offset: offset.value,
      limit: PAGE,
    })
  } catch (e) {
    pageDoc.value = null
    pageError.value = e.message
    msg.error(e.message)
  } finally {
    paging.value = false
  }
}

async function openLog() {
  const p = path.value.trim()
  if (!p) {
    catalog.value = null
    pageDoc.value = null
    error.value = t('exp.err.need_path')
    msg.warning(error.value)
    return
  }
  loading.value = true
  error.value = ''
  pageError.value = ''
  try {
    catalog.value = await api.post('/api/explain', { path: p })
    alignSelection()
    offset.value = 0
    await loadPage()
  } catch (e) {
    catalog.value = null
    pageDoc.value = null
    error.value = e.message
    msg.error(e.message)
  } finally {
    loading.value = false
  }
}

function pickLog(p) {
  path.value = p
  seed.value = ''
  fight.value = 0
  offset.value = 0
  openLog()
}
function pickSeed(v) {
  seed.value = v == null ? '' : String(v)
  fight.value = 0
  offset.value = 0
  loadPage()
}
function pickFight(v) {
  fight.value = typeof v === 'number' ? v : 0
  offset.value = 0
  loadPage()
}
function prevPage() {
  offset.value = Math.max(0, offset.value - PAGE)
  loadPage()
}
function nextPage() {
  if (!pageDoc.value || pageDoc.value.next_offset == null) return
  offset.value = pageDoc.value.next_offset
  loadPage()
}

async function find() {
  finding.value = true
  discoverError.value = ''
  try {
    const doc = await api.get('/api/explain/logs')
    logs.value = doc.logs || []
    truncated.value = !!doc.truncated
    foundOnce.value = true
  } catch (e) {
    discoverError.value = e.message
    msg.error(e.message)
  } finally {
    finding.value = false
  }
}

watch(() => route.query.path, (v, prev) => {
  const s = qstr(v)
  if (!s || s === qstr(prev)) return
  path.value = s
  seed.value = qstr(route.query.seed)
  fight.value = intQuery(route.query.fight)
  offset.value = 0
  openLog()
})
onMounted(() => { if (path.value.trim()) openLog() })
</script>

<style scoped>
.roots { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.root { text-align: left; background: #26262B; border: 1px solid #2E2E34; color: inherit; border-radius: 10px; padding: 8px 12px; cursor: pointer; }
.root:hover { border-color: #D97757; }
.picks { margin-top: 14px; }
.head { align-items: flex-start; gap: 16px; }
.head h3 { margin: 0; }
.decision { border: 1px solid #2E2E34; border-radius: 12px; padding: 14px 16px; margin-top: 12px; background: #19191C; }
.decision.close { border-color: rgba(224, 168, 108, .75); background: rgba(224, 168, 108, .08); }
.dh { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.kind { font-weight: 650; color: #F0A486; }
.turn { color: #B9B4AC; font-size: 13px; }
.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 650; }
.badge.close { background: rgba(224, 168, 108, .18); color: #E0A86C; }
.chosen { margin-top: 8px; display: flex; gap: 8px; align-items: baseline; }
.chosen .k { color: #9C978F; font-size: 12.5px; }
.margin { margin-top: 4px; font-size: 13px; color: #CFCAC2; }
.margin.close { color: #E0A86C; font-weight: 650; }
.cands { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }
.cands th { text-align: left; color: #9C978F; font-weight: 600; padding: 6px 8px; }
.cands td { padding: 6px 8px; border-top: 1px solid #2A2A30; }
.cands tr.picked td { color: #F0A486; }
.mech { color: #E0A86C; }
.pick { margin-left: 8px; font-size: 11px; letter-spacing: .04em; }
.pager { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.state { text-align: center; }
.state .big { font-size: 15px; color: #B9B4AC; margin-bottom: 8px; }
.state .detail { color: #CFCAC2; font-size: 13.5px; line-height: 1.55; text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; }
.hint.warn { color: #E0A86C; }
.page > .panel { margin-top: 16px; }
.page > .panel:first-child { margin-top: 0; }
</style>
