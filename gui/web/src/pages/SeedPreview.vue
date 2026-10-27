<template>
  <div class="page">
    <div class="layout">
      <div class="form">
        <div class="panel">
          <h3>{{ t('sp.seed') }}</h3>
          <div class="fields">
            <div>
              <div class="label">{{ t('sp.seed') }}</div>
              <n-input v-model:value="form.seed" :placeholder="t('sp.seedPh')" @keyup.enter="run" />
            </div>
            <div>
              <div class="label">{{ t('sp.char') }}</div>
              <n-select v-model:value="form.char" :options="charOptions" />
            </div>
            <div>
              <div class="label">{{ t('sp.asc') }} <b class="accent">A{{ form.asc }}</b></div>
              <n-slider v-model:value="form.asc" :min="0" :max="10" :step="1" :marks="{ 0: 'A0', 5: 'A5', 10: 'A10' }" />
            </div>
          </div>
          <div class="row" style="margin-top:16px">
            <n-checkbox v-model:checked="form.withRewards">{{ t('sp.withRewards') }}</n-checkbox>
            <n-button type="primary" :loading="loading" @click="run">{{ t('sp.show') }}</n-button>
          </div>
          <div class="hint">{{ t('sp.note') }}</div>
        </div>

        <div v-if="loading" class="panel empty"><n-spin /> <div class="big">{{ t('sp.working') }}</div></div>
        <div v-else-if="error" class="panel"><div class="err">{{ error }}</div></div>

        <template v-else-if="data">
          <div v-if="data.warnings && data.warnings.length" class="panel">
            <div v-for="(w, i) in data.warnings" :key="i" class="hint warn">{{ w }}</div>
          </div>

          <div class="panel">
            <h3>{{ t('sp.mapTitle', { act: actLabel(0) }) }}</h3>
            <div class="legend">
              <span v-for="tp in legendTypes" :key="tp" class="lg">
                <i :style="{ background: color[tp] }"></i>{{ t('sp.glyph.' + tp) }} {{ tr('room.', tp) }}
              </span>
            </div>
            <div v-if="fig" class="mapwrap">
              <svg :viewBox="`0 0 ${fig.width} ${fig.height}`" :width="fig.width" :height="fig.height" role="img">
                <text v-for="f in fig.floors" :key="'f' + f.r" :x="2" :y="f.y + 4" class="flabel">{{ f.r }}</text>
                <line v-for="(e, i) in fig.edges" :key="'e' + i" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2" stroke="#4A463F" stroke-width="2" />
                <g v-for="n in fig.nodes" :key="n.col + ':' + n.row">
                  <circle :cx="n.x" :cy="n.y" :r="fig.s / 2" :fill="color[n.type] || '#6E6A64'" />
                  <text :x="n.x" :y="n.y + 4" text-anchor="middle" class="glabel">{{ t('sp.glyph.' + n.type) }}</text>
                  <title>{{ tr('room.', n.type) }} {{ n.col }},{{ n.row }}</title>
                </g>
                <text v-for="c in fig.colNums" :key="'c' + c.c" :x="c.x" :y="fig.height - 4" text-anchor="middle" class="flabel">{{ c.c }}</text>
              </svg>
            </div>
            <div class="hint">{{ t('sp.mapCols') }}</div>
            <div v-if="mixText" class="mix">{{ t('sp.roomMix') }}{{ mixText }}</div>
          </div>

          <div class="panel">
            <h3>{{ t('sp.distTitle') }}</h3>
            <div class="hint">{{ t('sp.queueHint') }}</div>
            <div class="hint">{{ t('sp.unknownHint') }}</div>
            <div v-for="(act, i) in acts" :key="act.act || i" class="act">
              <div class="ah">{{ t('sp.actN', { n: i + 1 }) }} <b>{{ nm('acts', act.act) }}</b></div>
              <div v-if="act.boss" class="line"><span>{{ t('sp.boss') }}</span><b>{{ nm('encounters', act.boss) }}</b></div>
              <div v-if="act.second_boss" class="line"><span>{{ t('sp.secondBoss') }}</span><b>{{ nm('encounters', act.second_boss) }}</b></div>
              <div v-if="act.ancient" class="line"><span>{{ t('sp.ancient') }}</span><b>{{ nm('ancients', act.ancient) }}</b></div>
              <div class="line"><span>{{ t('sp.normal') }}</span><b>{{ orderText(act.normal) }}</b></div>
              <div class="line"><span>{{ t('sp.elite') }}</span><b>{{ orderText(act.elite) }}</b></div>
              <div v-if="act.events && act.events.order && act.events.order.length" class="line"><span>{{ t('sp.events') }}</span><b>{{ orderText(act.events) }}</b></div>
            </div>
          </div>

          <div class="panel">
            <h3>{{ t('sp.notable') }}</h3>
            <div class="line"><span>{{ t('sp.startingRelics') }}</span><b>{{ listText('relics', notable.relics) }}</b></div>
            <div class="line"><span>{{ t('sp.startingDeck') }}</span><b>{{ listText('cards', notable.deck) }}</b></div>
            <div v-if="notable.gold !== null && notable.gold !== undefined" class="line"><span>{{ t('sp.gold') }}</span><b>{{ notable.gold }}</b></div>
            <div v-if="data.ancient" class="line"><span>{{ t('sp.neowTitle') }}</span><b>{{ nm('ancients', data.ancient) }}</b></div>
            <div v-for="o in data.neow_options || []" :key="o.index" class="opt">
              <span class="idx">[{{ o.index }}]</span>
              <span>{{ (data.labels && data.labels.neow && data.labels.neow[o.key]) || o.id || o.key }}</span>
              <span v-if="o.locked" class="lock">{{ t('sp.locked') }}</span>
            </div>
            <div v-for="(block, idx) in rewardBlocks" :key="'rw' + idx" class="reward">
              <div v-if="block.error" class="err">{{ t('sp.failed', { err: block.error }) }}</div>
              <template v-else>
                <div class="rh">{{ t('sp.firstReward', { index: block.index, encounter: nm('encounters', block.encounter) || t('sp.none') }) }}</div>
                <div v-for="(rw, j) in block.rewards || []" :key="j" class="ro">{{ rewardText(rw) }}</div>
              </template>
            </div>
          </div>
        </template>
      </div>

      <div class="aside">
        <div class="panel sticky">
          <div class="sec-title">{{ t('sp.summary') }}</div>
          <pre v-if="data" class="sumtext">{{ data.summary }}</pre>
          <div v-else class="hint">{{ t('sp.note') }}</div>
          <n-button v-if="data" secondary block style="margin-top:12px" @click="copySummary">{{ t('sp.copy') }}</n-button>
          <n-button v-if="data" type="primary" block style="margin-top:8px" @click="playThis">{{ t('sp.play') }}</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCheckbox, NInput, NSelect, NSlider, NSpin, useMessage } from 'naive-ui'
import { api, store } from '../api'
import { t, tr, joinList } from '../i18n'

const IDS = ['Ironclad', 'Silent', 'Defect', 'Necrobinder', 'Regent']
const legendTypes = ['Monster', 'Elite', 'Unknown', 'Shop', 'RestSite', 'Treasure', 'Boss', 'Ancient']
const color = {
  Monster: '#7FA7C9', Elite: '#E38B6D', Unknown: '#6E6A64', Shop: '#E3B47E',
  RestSite: '#8FBF8F', Treasure: '#B79CE0', Boss: '#E06C6C', Ancient: '#D98FA6', Unassigned: '#5C5954',
}

const router = useRouter()
const msg = useMessage()
const form = reactive({ seed: '', char: 'Ironclad', asc: 0, withRewards: true })
const loading = ref(false)
const error = ref('')
const data = ref(null)

const charOptions = computed(() => IDS.map((id) => ({ value: id, label: store.charName(id) })))
const acts = computed(() => (data.value && data.value.distribution && data.value.distribution.acts) || [])
const notable = computed(() => (data.value && data.value.notable) || {})
const mixText = computed(() => {
  const mix = data.value && data.value.distribution && data.value.distribution.map_rooms
  if (!mix || !mix.length) return ''
  return joinList(mix.map((it) => t('sp.times', { name: tr('room.', it.type), n: it.count })))
})
const rewardBlocks = computed(() => {
  const after = (data.value && data.value.after_neow) || {}
  return Object.keys(after).sort((a, b) => Number(a) - Number(b)).map((k) => ({ index: k, ...after[k] }))
})

function nm(bucket, id) {
  if (!id) return ''
  const table = data.value && data.value.labels && data.value.labels[bucket]
  return (table && table[id]) || id
}
function actLabel(i) {
  const a = acts.value[i]
  return a ? nm('acts', a.act) : t('sp.actN', { n: i + 1 })
}
function orderText(block) {
  const ids = (block && block.order) || []
  if (!ids.length) return t('sp.none')
  return ids.map((id, i) => `${i + 1}. ${nm('encounters', id)}`).join(t('sep.list'))
}
function listText(bucket, ids) {
  if (!ids || !ids.length) return t('sp.none')
  return joinList(ids.map((id) => nm(bucket, id)))
}
function rewardText(rw) {
  const bits = []
  if (rw.cards && rw.cards.length) bits.push(t('sp.cards') + ' ' + joinList(rw.cards.map((c) => nm('cards', c))))
  if (rw.gold !== undefined && rw.gold !== null) bits.push(t('sp.goldReward', { n: rw.gold }))
  if (rw.potion) bits.push(t('sp.potion') + ' ' + nm('potions', rw.potion))
  if (rw.relic) bits.push(t('sp.relic') + ' ' + nm('relics', rw.relic))
  return bits.join(t('sep.problems')) || rw.kind || ''
}

const fig = computed(() => {
  const mp = data.value && data.value.map
  if (!mp) return null
  const S = 30, GX = 28, GY = 36, left = 26, top = 18
  const by = {}
  for (const row of mp.rows || []) for (const n of row) by[n.col + ':' + n.row] = n
  const boss = mp.boss
  if (boss && !by[boss.col + ':' + boss.row]) by[boss.col + ':' + boss.row] = { col: boss.col, row: boss.row, type: 'Boss', children: [] }
  const nodes = Object.values(by)
  if (!nodes.length) return null
  const maxRow = Math.max(...nodes.map((n) => n.row))
  const cols = mp.cols || Math.max(...nodes.map((n) => n.col)) + 1
  const pos = (col, row) => [left + col * (S + GX) + S / 2, top + (maxRow - row) * (S + GY) + S / 2]
  const edges = []
  for (const n of nodes) {
    const [x1, y1] = pos(n.col, n.row)
    for (const ch of n.children || []) {
      const [x2, y2] = pos(ch[0], ch[1])
      edges.push({ x1, y1, x2, y2 })
    }
  }
  const width = left + cols * (S + GX) + 10
  const height = top + (maxRow + 1) * (S + GY) + 16
  return {
    width, height, s: S, edges,
    nodes: nodes.map((n) => ({ ...n, x: pos(n.col, n.row)[0], y: pos(n.col, n.row)[1] })),
    floors: Array.from({ length: maxRow }, (_, i) => ({ r: maxRow - i, y: pos(0, maxRow - i)[1] })).filter((f) => f.r > 0),
    colNums: Array.from({ length: cols }, (_, c) => ({ c, x: pos(c, 1)[0] })),
  }
})

async function run() {
  error.value = ''
  loading.value = true
  data.value = null
  try {
    data.value = await api.post('/api/seed-preview', {
      seed: form.seed, char: form.char, asc: form.asc, neow: form.withRewards ? 'all' : 'none',
    })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
async function copySummary() {
  try {
    await navigator.clipboard.writeText((data.value && data.value.summary) || '')
    msg.success(t('sp.copied'))
  } catch (e) {
    msg.error(e.message)
  }
}
function playThis() {
  if (!data.value) return
  let saved = {}
  try { saved = JSON.parse(localStorage.getItem('nt.form') || '{}') } catch (e) { saved = {} }
  const b = Object.assign({}, saved.b || {}, { char: form.char, asc: form.asc, gameSeed: data.value.seed, n: 1 })
  localStorage.setItem('nt.form', JSON.stringify(Object.assign({}, saved, { b })))
  localStorage.setItem('nt.kind', 'batch')
  router.push('/new')
}
</script>

<style scoped>
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; align-items: start; }
.fields { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 16px; }
.form { min-width: 0; }
.aside { min-width: 0; }
.sticky { position: sticky; top: 18px; }
.err { color: #E06C6C; font-size: 13.5px; line-height: 1.5; }
.hint.warn { color: #E3B47E; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-bottom: 12px; }
.lg { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #B9B4AC; }
.lg i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.mapwrap { overflow-x: auto; background: #18181B; border: 1px solid #2E2E34; border-radius: 12px; padding: 8px; }
.flabel { fill: #77736C; font-size: 11px; }
.glabel { fill: #1B1B1E; font-size: 12px; font-weight: 700; }
.mix { margin-top: 10px; font-size: 13px; color: #CFCAC2; }
.act { margin-top: 14px; padding-top: 10px; border-top: 1px solid #2E2E34; }
.act:first-of-type { border-top: 0; padding-top: 4px; }
.ah { font-weight: 650; margin-bottom: 6px; }
.line { display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: 8px; font-size: 13px; padding: 3px 0; }
.line span { color: #9C978F; }
.line b { font-weight: 550; }
.opt { display: flex; gap: 8px; align-items: baseline; font-size: 13.5px; padding: 3px 0; }
.idx { color: #F0A486; font-variant-numeric: tabular-nums; }
.lock { color: #E3B47E; font-size: 12px; }
.reward { margin-top: 10px; }
.rh { font-size: 13px; color: #E4DFD8; margin-bottom: 4px; }
.ro { font-size: 13px; color: #CFCAC2; padding-left: 8px; }
.sumtext { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 11.5px; line-height: 1.45; color: #CFCAC2; max-height: 70vh; overflow: auto; font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace; }
@media (max-width: 980px) {
  .layout { grid-template-columns: 1fr; }
  .fields { grid-template-columns: 1fr; }
  .sticky { position: static; }
  .line { grid-template-columns: 110px minmax(0, 1fr); }
}
</style>
