<template>
  <div class="panel" style="margin-top:16px">
    <div class="row between">
      <h3 style="margin:0">{{ run.seed || t('common.none') }}</h3>
      <n-button v-if="run.seed" size="small" secondary @click="openPreview">{{ t('imp.openPreview') }}</n-button>
    </div>
    <div v-if="run.seed && !run.sim_character" class="hint">{{ t('imp.previewCharUnknown') }}</div>
    <div class="grid g4" style="margin-top:14px">
      <div><div class="label">{{ t('imp.character') }}</div><b>{{ who }}</b></div>
      <div><div class="label">{{ t('imp.ascension') }}</div><b>A{{ run.ascension }}</b></div>
      <div><div class="label">{{ t('imp.result') }}</div><b>{{ t('imp.result.' + run.result) }}</b></div>
      <div><div class="label">{{ t('imp.schema') }}</div><b class="mono">{{ run.schema_version ?? t('common.none') }}</b></div>
    </div>
    <div class="hint">{{ t('imp.acts') }}: <span class="mono">{{ acts }}</span></div>
    <div v-if="run.killed_by_encounter || run.killed_by_event" class="hint">
      {{ t('imp.killedBy') }}: <span class="mono">{{ run.killed_by_encounter || run.killed_by_event }}</span>
    </div>
    <div v-for="w in run.warnings || []" :key="w.code + (w.act || '')" class="hint">{{ warnText(w) }}</div>

    <div v-for="act in maps" :key="act.index" style="margin-top:16px">
      <div class="label">{{ t('imp.acts') }} {{ act.index + 1 }} <span class="mono">{{ act.id }}</span></div>
      <map-grid :map="act.map" :path="act.index === run.current_act_index ? run.visited_map_coords : []" />
    </div>

    <h3 style="margin-top:18px">{{ t('imp.route') }}</h3>
    <table v-if="run.route && run.route.length" class="gridish">
      <thead>
        <tr>
          <th>{{ t('imp.floor') }}</th>
          <th>{{ t('imp.acts') }}</th>
          <th>{{ t('imp.type') }}</th>
          <th>{{ t('imp.rooms') }}</th>
          <th>{{ t('imp.picks') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in run.route" :key="f.floor">
          <td>{{ f.floor }}</td>
          <td class="mono">{{ f.act || (f.act_index + 1) }}</td>
          <td>{{ typeName(f.type) }}</td>
          <td class="mono">{{ rooms(f) }}</td>
          <td>{{ picks(f) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="hint">{{ t('common.none') }}</div>

    <div class="grid g2" style="margin-top:18px">
      <div>
        <h3>{{ t('imp.relics') }}</h3>
        <div v-if="!relics.length" class="hint">{{ t('imp.noRelics') }}</div>
        <div v-for="(r, i) in relics" :key="i" class="line mono">{{ r.who }}{{ r.id }}<span v-if="r.floor != null" class="faint">{{ t('imp.floorAdded', { floor: r.floor }) }}</span></div>
      </div>
      <div>
        <h3>{{ t('imp.deck') }}</h3>
        <div v-if="!deck.length" class="hint">{{ t('imp.noDeck') }}</div>
        <div v-for="(c, i) in deck" :key="i" class="line mono">{{ c.who }}{{ c.id }}<span v-if="c.upgraded">+</span><span v-if="c.floor != null" class="faint">{{ t('imp.floorAdded', { floor: c.floor }) }}</span><span v-if="c.enchantment" class="faint"> {{ t('imp.enchant', { id: c.enchantment.id }) }}</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { t, has } from '../i18n'
import MapGrid from './MapGrid.vue'

const props = defineProps({ run: { type: Object, required: true } })
const router = useRouter()
const acts = computed(() => (props.run.acts || []).map((a) => a.id).filter(Boolean).join(' → '))
const maps = computed(() => (props.run.acts || []).filter((a) => a.map))
const many = computed(() => (props.run.players || []).length > 1)
const relics = computed(() => (props.run.players || []).flatMap((p) => (p.relics || []).map((r) => ({ ...r, who: many.value ? `P${p.id} ` : '' }))))
const deck = computed(() => (props.run.players || []).flatMap((p) => (p.deck || []).map((c) => ({ ...c, who: many.value ? `P${p.id} ` : '' }))))
const who = computed(() => (props.run.players || []).map((p) => p.character || t('common.none')).join(', ') || t('common.none'))

function warnText(w) {
  const k = 'imp.warn.' + (w.code || '')
  return has(k) ? t(k, w) : (w.code || '')
}
function typeName(typ) {
  if (!typ) return t('common.none')
  return has('mp.' + typ) ? t('mp.' + typ) : typ
}
function rooms(f) {
  const ids = (f.rooms || []).map((r) => r.model_id).filter(Boolean)
  return ids.length ? ids.join(', ') : t('common.none')
}
function picks(f) {
  const parts = []
  for (const g of f.picks || []) {
    const picked = (g.cards || []).filter((c) => c.was_picked).map((c) => c.id)
    const offered = (g.cards || []).map((c) => c.id)
    if (!offered.length) continue
    parts.push(t('imp.picked') + ' ' + (picked.join(', ') || t('imp.skipped')) + ' / ' + t('imp.offered') + ' ' + offered.join(', '))
  }
  return parts.join(' · ') || t('imp.noPicks')
}
function openPreview() {
  router.push({ path: '/preview', query: { seed: props.run.seed, char: props.run.sim_character || 'Ironclad', asc: String(props.run.ascension || 0) } })
}
</script>

<style scoped>
.line { padding: 4px 0; font-size: 13px; }
.gridish { width: 100%; border-collapse: collapse; font-size: 13px; }
.gridish th { text-align: left; color: #9C978F; font-weight: 600; padding: 6px 8px; }
.gridish td { padding: 8px; border-top: 1px solid #2A2A30; vertical-align: top; }
</style>
