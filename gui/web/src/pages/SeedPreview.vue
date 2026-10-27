<template>
  <div class="page">
    <div class="panel">
      <div class="grid g4">
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
        <div>
          <div class="label">{{ t('prev.neow') }}</div>
          <n-select v-model:value="neow" :options="neowOpts" />
        </div>
      </div>
      <n-button type="primary" style="margin-top:16px" :loading="loading" @click="run">{{ t('prev.run') }}</n-button>
    </div>

    <div v-if="error" class="panel empty" style="margin-top:16px"><div class="big">{{ error }}</div></div>
    <div v-else-if="loading" class="panel empty" style="margin-top:16px"><n-spin /><div class="hint">{{ t('prev.loading') }}</div></div>

    <template v-else-if="res">
      <div class="grid g4" style="margin-top:16px">
        <div class="stat"><div class="k">{{ t('prev.seed') }}</div><div class="v mono" style="font-size:18px">{{ res.seed }}</div></div>
        <div class="stat"><div class="k">{{ t('prev.character') }}</div><div class="v" style="font-size:18px">{{ res.character }}</div></div>
        <div class="stat"><div class="k">{{ t('prev.ascension') }}</div><div class="v">A{{ res.ascension }}</div></div>
        <div class="stat"><div class="k">{{ t('imp.acts') }}</div><div class="v mono" style="font-size:14px">{{ (res.acts || []).join(' · ') }}</div></div>
      </div>

      <div v-if="res.warnings && res.warnings.length" class="panel" style="margin-top:16px">
        <h3>{{ t('prev.warnings') }}</h3>
        <div v-for="(w, i) in res.warnings" :key="i" class="hint">{{ warnText(w) }}</div>
      </div>

      <div v-for="mp in res.maps || []" :key="mp.act_index" class="panel" style="margin-top:16px">
        <h3>{{ t('prev.map') }} {{ mp.act_index + 1 }} <span class="mono">{{ mp.act }}</span></h3>
        <div class="hint">{{ confText(mp.confidence) }}</div>
        <div v-if="mp.error" class="hint">{{ mp.error }}</div>
        <map-grid :map="mp" />
        <div v-if="mp.counts && Object.keys(mp.counts).length" class="legend">
          <span v-for="(n, k) in mp.counts" :key="k" class="chip">{{ typeName(k) }} {{ n }}</span>
        </div>
      </div>

      <div class="panel" style="margin-top:16px">
        <h3>{{ t('prev.distribution') }}</h3>
        <div v-for="d in res.distribution || []" :key="d.act" class="act">
          <div class="label mono">{{ d.act }}</div>
          <div class="hint">{{ t('prev.boss') }} <span class="mono">{{ d.boss || t('common.none') }}</span>
            · {{ t('prev.secondBoss') }} <span class="mono">{{ d.second_boss || t('common.none') }}</span>
            · {{ t('prev.ancient') }} <span class="mono">{{ d.ancient || t('common.none') }}</span></div>
          <div class="hint">{{ t('prev.normal') }}: <span class="mono">{{ (d.normal || []).join(', ') || t('common.none') }}</span></div>
          <div class="hint">{{ t('prev.elite') }}: <span class="mono">{{ (d.elite || []).join(', ') || t('common.none') }}</span></div>
        </div>
      </div>

      <div class="panel" style="margin-top:16px">
        <h3>{{ t('prev.neow') }} <span class="mono faint">{{ res.ancient }}</span></h3>
        <div v-if="!(res.neow_options || []).length" class="hint">{{ t('common.none') }}</div>
        <div v-for="o in res.neow_options || []" :key="o.index" class="line mono">[{{ o.index }}] {{ o.id }}<span v-if="o.locked" class="faint">{{ t('prev.locked') }}</span></div>
        <h3 style="margin-top:16px">{{ t('prev.rewards') }}</h3>
        <div v-if="!Object.keys(res.after_neow || {}).length" class="hint">{{ t('common.none') }}</div>
        <div v-for="(block, idx) in res.after_neow || {}" :key="idx" class="act">
          <div class="label">{{ t('prev.rewardFor', { index: idx }) }}</div>
          <div v-if="block.error" class="hint">{{ block.error }}</div>
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

      <div class="panel" style="margin-top:16px">
        <h3>{{ t('prev.startingRelics') }}</h3>
        <div class="mono">{{ (res.relics && res.relics.starting || []).join(', ') || t('common.none') }}</div>
        <h3 style="margin-top:14px">{{ t('prev.sharedQueue') }}</h3>
        <div class="mono">{{ (res.relics && res.relics.shared_queue || []).join(', ') || t('prev.noQueue') }}</div>
        <h3 style="margin-top:14px">{{ t('prev.characterQueue') }}</h3>
        <div class="mono">{{ (res.relics && res.relics.character_queue || []).join(', ') || t('prev.noQueue') }}</div>
        <div class="hint">{{ t('prev.relicNote') }}</div>
      </div>

      <div class="panel" style="margin-top:16px">
        <h3>{{ t('prev.limitsTitle') }}</h3>
        <div v-for="code in res.limits || []" :key="code" class="hint">{{ limitText(code) }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NInput, NSelect, NSlider, NSpin, useMessage } from 'naive-ui'
import { api, store } from '../api'
import { t, has } from '../i18n'
import MapGrid from '../components/MapGrid.vue'

const route = useRoute()
const msg = useMessage()
const BASE = ['Ironclad', 'Silent', 'Defect', 'Necrobinder', 'Regent']
const seed = ref(String(route.query.seed || ''))
const charId = ref(String(route.query.char || 'Ironclad'))
const asc = ref(Number(route.query.asc || 0))
const neow = ref('first')
const loading = ref(false)
const error = ref('')
const res = ref(null)
const chars = computed(() => {
  const fromCat = (store.catalog && store.catalog.characters || []).filter((c) => BASE.includes(c.id))
  const list = fromCat.length ? fromCat : BASE.map((id) => ({ id, name: id }))
  return list.map((c) => ({ label: c.name, value: c.id }))
})
const neowOpts = computed(() => [
  { label: t('prev.neowFirst'), value: 'first' },
  { label: t('prev.neowAll'), value: 'all' },
  { label: t('prev.neowNone'), value: 'none' },
])
watch(() => route.query.seed, (v) => { if (v) seed.value = String(v) })
watch(() => route.query.char, (v) => { if (v && BASE.includes(String(v))) charId.value = String(v) })
watch(() => route.query.asc, (v) => { if (v != null && v !== '') asc.value = Number(v) })
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
function typeName(k) { return has('mp.' + k) ? t('mp.' + k) : k }
async function run() {
  loading.value = true
  error.value = ''
  try {
    res.value = await api.post('/api/seed-preview', { seed: seed.value, char: charId.value, asc: asc.value, neow: neow.value })
  } catch (e) { res.value = null; error.value = e.message; msg.error(e.message) }
  finally { loading.value = false }
}
</script>

<style scoped>
.empty { text-align: center; }
.big { font-size: 15px; }
.line { padding: 3px 0; font-size: 13px; }
.act + .act { margin-top: 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.accent { color: #F0A486; }
</style>
