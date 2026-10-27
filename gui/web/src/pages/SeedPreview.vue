<template>
  <div class="page">
    <div class="panel">
      <div class="grid g3">
        <div>
          <div class="label">{{ t('prev.seed') }}</div>
          <n-input v-model:value="seed" :placeholder="t('prev.seedPh')" @keyup.enter="run" />
        </div>
        <div>
          <div class="label">{{ t('prev.character') }}</div>
          <n-select v-model:value="charId" :options="chars" />
        </div>
        <div>
          <div class="label">{{ t('prev.ascension') }} <b class="accent">A{{ asc }}</b></div>
          <n-slider v-model:value="asc" :min="0" :max="10" :step="1" />
        </div>
      </div>
      <div class="neow">
        <div class="label">{{ t('prev.neowScope') }}</div>
        <n-radio-group v-model:value="neow">
          <n-radio-button value="first">{{ t('prev.neowFirst') }}</n-radio-button>
          <n-radio-button value="all">{{ t('prev.neowAll') }}</n-radio-button>
          <n-radio-button value="none">{{ t('prev.neowNone') }}</n-radio-button>
          <n-radio-button v-if="neowIsIndex" :value="neow">{{ t('prev.neowIndex', { n: neow }) }}</n-radio-button>
        </n-radio-group>
        <div class="hint">{{ neowHintText }}</div>
        <div v-if="staleNeow" class="hint warn">{{ t('prev.neowStale') }}</div>
      </div>
      <n-button type="primary" style="margin-top:16px" :loading="loading" @click="run">{{ t('prev.run') }}</n-button>
    </div>

    <div v-if="error" class="panel state">
      <div class="big">{{ noEngine ? t('prev.noEngineTitle') : t('prev.errTitle') }}</div>
      <div class="detail">{{ error }}</div>
      <div v-if="noEngine" class="hint">{{ t('prev.noEngineHint') }}</div>
    </div>
    <div v-else-if="loading" class="panel state"><n-spin /><div class="hint">{{ t('prev.loading') }}</div></div>

    <template v-else-if="res">
      <div class="grid g4" style="margin-top:16px">
        <div class="stat"><div class="k">{{ t('prev.seed') }}</div><div class="v mono" style="font-size:18px">{{ res.seed }}</div></div>
        <div class="stat"><div class="k">{{ t('prev.character') }}</div><div class="v" style="font-size:18px">{{ res.character }}</div></div>
        <div class="stat"><div class="k">{{ t('prev.ascension') }}</div><div class="v">A{{ res.ascension }}</div></div>
        <div class="stat"><div class="k">{{ t('imp.acts') }}</div><div class="v mono" style="font-size:14px">{{ (res.acts || []).join(' · ') }}</div></div>
      </div>

      <div v-if="res.warnings && res.warnings.length" class="panel">
        <h3>{{ t('prev.warnings') }}</h3>
        <div v-for="(w, i) in res.warnings" :key="i" class="hint warn">{{ warnText(w) }}</div>
      </div>

      <div v-if="hasProjected" class="panel note-panel">
        <div class="hint warn" style="margin:0">{{ t('prev.projectedNote') }}</div>
      </div>

      <div v-for="mp in res.maps || []" :key="mp.act_index" class="panel">
        <div class="map-head">
          <h3>{{ t('prev.actHeading', { n: mp.act_index + 1 }) }} <span class="mono">{{ mp.act }}</span></h3>
          <span v-if="mp.confidence" class="badge" :class="mp.confidence">{{ badgeText(mp.confidence) }}</span>
        </div>
        <div class="hint">{{ confText(mp.confidence) }}</div>
        <div v-if="mp.error || mp.confidence === 'failed'" class="hint warn">
          {{ t('prev.mapMissing') }}
          <div v-if="mp.error" class="mono">{{ mp.error }}</div>
        </div>
        <map-grid v-else :map="mp" />
        <div v-if="mp.counts && Object.keys(mp.counts).length" class="legend">
          <span v-for="(n, k) in mp.counts" :key="k" class="chip">{{ typeName(k) }} {{ n }}</span>
        </div>
      </div>

      <div class="panel">
        <h3>{{ t('prev.distribution') }}</h3>
        <div class="hint">{{ t('prev.distributionHint') }}</div>
        <div v-for="(d, i) in res.distribution || []" :key="(d.act || '') + i" class="act">
          <div class="label mono">{{ t('prev.actHeading', { n: i + 1 }) }} {{ d.act }}</div>
          <div class="hint">{{ t('prev.boss') }} <span class="mono">{{ d.boss || t('common.none') }}</span>
            · {{ t('prev.secondBoss') }} <span class="mono">{{ d.second_boss || t('common.none') }}</span>
            · {{ t('prev.ancient') }} <span class="mono">{{ d.ancient || t('common.none') }}</span></div>
          <div class="hint">{{ t('prev.normal') }}: <span class="mono">{{ (d.normal || []).join(', ') || t('common.none') }}</span></div>
          <div class="hint">{{ t('prev.elite') }}: <span class="mono">{{ (d.elite || []).join(', ') || t('common.none') }}</span></div>
        </div>
      </div>

      <div class="panel">
        <h3>{{ t('prev.neow') }} <span class="mono faint">{{ res.ancient }}</span></h3>
        <div v-if="!(res.neow_options || []).length" class="hint">{{ t('common.none') }}</div>
        <div v-for="o in res.neow_options || []" :key="o.index" class="line mono" :class="{ locked: o.locked }">[{{ o.index }}] {{ o.id }}<span v-if="o.locked" class="lock">{{ t('prev.locked') }}</span></div>
        <h3 style="margin-top:16px">{{ t('prev.rewards') }}</h3>
        <div class="hint">{{ neowHintText }}</div>
        <div v-if="!Object.keys(res.after_neow || {}).length" class="hint">{{ t('common.none') }}</div>
        <div v-for="(block, idx) in res.after_neow || {}" :key="idx" class="act">
          <div class="label">{{ t('prev.rewardFor', { index: idx }) }}</div>
          <div v-if="block.error" class="hint warn">{{ block.error }}</div>
          <template v-else>
            <div class="hint">{{ t('prev.encounter') }} <span class="mono">{{ block.encounter }}</span></div>
            <div v-for="(rw, i) in block.rewards || []" :key="i" class="line mono">
              <template v-if="rw.cards">{{ t('prev.cards') }} {{ rw.cards.join(' / ') }}</template>
              <template v-else-if="rw.gold != null">{{ t('prev.gold') }} {{ rw.gold }}</template>
              <template v-else-if="rw.potion">{{ t('prev.potion') }} {{ rw.potion }}</template>
              <template v-else-if="rw.relic">{{ t('prev.relic') }} {{ rw.relic }}</template>
            </div>
          </template>
        </div>
      </div>

      <div class="panel">
        <h3>{{ t('prev.startingRelics') }}</h3>
        <div class="mono">{{ (res.relics && res.relics.starting || []).join(', ') || t('common.none') }}</div>
        <h3 style="margin-top:14px">{{ t('prev.sharedQueue') }}</h3>
        <div class="mono">{{ (res.relics && res.relics.shared_queue || []).join(', ') || t('prev.noQueue') }}</div>
        <h3 style="margin-top:14px">{{ t('prev.characterQueue') }}</h3>
        <div class="mono">{{ (res.relics && res.relics.character_queue || []).join(', ') || t('prev.noQueue') }}</div>
        <div class="hint">{{ t('prev.relicNote') }}</div>
      </div>

      <div class="panel">
        <h3>{{ t('prev.limitsTitle') }}</h3>
        <div v-for="code in res.limits || []" :key="code" class="hint">{{ limitText(code) }}</div>
      </div>
    </template>

    <div v-else-if="store.catalogError" class="panel state">
      <div class="big">{{ t('prev.noEngineTitle') }}</div>
      <div v-if="catalogLine" class="detail">{{ catalogLine }}</div>
      <div class="hint">{{ t('prev.noEngineHint') }}</div>
    </div>
    <div v-else class="panel state">
      <div class="big">{{ t('prev.emptyTitle') }}</div>
      <div class="detail">{{ t('prev.emptyHint') }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NInput, NRadioButton, NRadioGroup, NSelect, NSlider, NSpin, useMessage } from 'naive-ui'
import { api, store } from '../api'
import { t, has } from '../i18n'
import MapGrid from '../components/MapGrid.vue'

const route = useRoute()
const msg = useMessage()
const BASE = ['Ironclad', 'Silent', 'Defect', 'Necrobinder', 'Regent']

function qstr(v) {
  if (Array.isArray(v)) v = v[0]
  return v == null ? '' : String(v)
}
function neowFromQuery(v) {
  const s = qstr(v).trim()
  if (s === 'first' || s === 'all' || s === 'none' || /^\d+$/.test(s)) return s
  return ''
}
function ascFromQuery(v) {
  const s = qstr(v)
  const n = Number(s)
  if (s === '' || !Number.isFinite(n)) return 0
  return Math.min(10, Math.max(0, Math.trunc(n)))
}

const seed = ref(qstr(route.query.seed))
const charId = ref(BASE.includes(qstr(route.query.char)) ? qstr(route.query.char) : 'Ironclad')
const asc = ref(ascFromQuery(route.query.asc))
const neow = ref(neowFromQuery(route.query.neow) || 'first')
const appliedNeow = ref('')
const loading = ref(false)
const error = ref('')
const res = ref(null)
const chars = computed(() => {
  const fromCat = (store.catalog && store.catalog.characters || []).filter((c) => BASE.includes(c.id))
  const list = fromCat.length ? fromCat : BASE.map((id) => ({ id, name: id }))
  return list.map((c) => ({ label: c.name, value: c.id }))
})
const neowIsIndex = computed(() => /^\d+$/.test(String(neow.value)))
const neowHintText = computed(() => {
  if (neow.value === 'all') return t('prev.neowHint.all')
  if (neow.value === 'none') return t('prev.neowHint.none')
  if (neowIsIndex.value) return t('prev.neowHint.index', { n: neow.value })
  return t('prev.neowHint.first')
})
const staleNeow = computed(() => !!(appliedNeow.value && appliedNeow.value !== neow.value && res.value))
const hasProjected = computed(() => (res.value && res.value.maps || []).some((m) => m.confidence === 'projected'))
const catalogLine = computed(() => {
  const line = String(store.catalogError || '').split('\n').map((x) => x.trim()).filter(Boolean)[0] || ''
  return line.length > 200 ? line.slice(0, 200) + '...' : line
})
const noEngine = computed(() => {
  if (!error.value) return false
  const head = t('prev.err.no_engine', { err: '' }).trim()
  return !!head && error.value.startsWith(head)
})
watch(() => route.query.seed, (v, prev) => {
  const s = qstr(v)
  if (!s || s === qstr(prev)) return
  seed.value = s
  run()
})
watch(() => route.query.char, (v) => { const s = qstr(v); if (s && BASE.includes(s)) charId.value = s })
watch(() => route.query.asc, (v) => { if (qstr(v) !== '') asc.value = ascFromQuery(v) })
watch(() => route.query.neow, (v) => { const s = neowFromQuery(v); if (s) neow.value = s })
onMounted(() => { if (seed.value.trim()) run() })

function warnText(w) {
  if (typeof w === 'string') return w
  const k = 'prev.warn.' + (w.code || '')
  return has(k) ? t(k, w) : (w.text || w.code || '')
}
function limitText(code) {
  const k = 'prev.limit.' + code
  return has(k) ? t(k) : code
}
function confText(code) {
  const k = 'prev.confidence.' + code
  return has(k) ? t(k) : (code || '')
}
function badgeText(code) {
  if (code === 'act_entry') return t('prev.badge.act_entry')
  if (code === 'projected') return t('prev.badge.projected')
  if (code === 'failed') return t('prev.badge.failed')
  return confText(code)
}
function typeName(k) { return has('mp.' + k) ? t('mp.' + k) : k }
async function run() {
  if (!seed.value.trim()) {
    res.value = null
    appliedNeow.value = ''
    error.value = t('prev.err.need_seed')
    msg.warning(error.value)
    return
  }
  loading.value = true
  error.value = ''
  try {
    res.value = await api.post('/api/seed-preview', { seed: seed.value, char: charId.value, asc: asc.value, neow: neow.value })
    appliedNeow.value = neow.value
  } catch (e) {
    res.value = null
    appliedNeow.value = ''
    error.value = e.message
    msg.error(e.message)
  } finally { loading.value = false }
}
</script>

<style scoped>
.state { text-align: center; }
.state .big { font-size: 15px; color: #B9B4AC; margin-bottom: 8px; }
.state .detail { color: #CFCAC2; font-size: 13.5px; line-height: 1.55; text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; }
.line { padding: 3px 0; font-size: 13px; }
.line.locked { color: #8A857E; }
.lock { margin-left: 6px; }
.act + .act { margin-top: 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.accent { color: #F0A486; }
.hint.warn { color: #E0A86C; }
.neow { margin-top: 16px; }
.neow :deep(.n-radio-group) { display: flex; flex-wrap: wrap; gap: 8px; }
.map-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.map-head h3 { margin: 0; }
.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 650; letter-spacing: .01em; }
.badge.act_entry { background: rgba(143, 184, 201, .18); color: #B7D4E0; }
.badge.projected { background: rgba(224, 168, 108, .16); color: #E0A86C; }
.badge.failed { background: rgba(224, 108, 108, .16); color: #E07A7A; }
.note-panel { padding-top: 14px; padding-bottom: 14px; }
.page > .panel { margin-top: 16px; }
.page > .panel:first-child { margin-top: 0; }
</style>
