<template>
  <div class="trs">
    <div v-if="!list.length" class="none">{{ t('me.t.empty') }}</div>
    <div v-for="(tr, i) in list" :key="i" class="tr">
      <div class="th">
        <span class="lbl">{{ t('me.t.when') }}</span>
        <n-select size="small" class="kind" :value="kindOf(tr)" :options="kindOptions" filterable @update:value="(k) => setKind(i, k)" />
        <div class="sp"></div>
        <n-button quaternary size="tiny" @click="more[i] = !more[i]"><template #icon><n-icon :component="Adjustments" /></template></n-button>
        <n-button quaternary size="tiny" @click="remove(i)"><template #icon><n-icon :component="Trash" /></template></n-button>
      </div>
      <div class="params">
        <mod-param v-for="p in shownParams(tr, i)" :key="p.name" :spec="p" :model-value="tr[p.name]" :schema="schema" :ctx="ctx"
                   @update:model-value="(v) => setParam(i, p.name, v)" />
        <template v-if="more[i] || tr.if || tr.once">
          <div class="mp2"><div class="pl">{{ t('me.e.if') }}</div>
            <n-input size="small" class="mono" :value="tr.if || ''" :placeholder="t('me.e.ifPh')" @update:value="(v) => setParam(i, 'if', v || undefined)" /></div>
          <div class="mp2"><div class="pl">{{ t('me.e.once') }}</div>
            <n-select size="small" :value="tr.once || null" :options="onceOptions" clearable :placeholder="t('me.e.onceNone')" @update:value="(v) => setParam(i, 'once', v || undefined)" /></div>
        </template>
      </div>
    </div>
    <n-dropdown trigger="click" :options="addOptions" scrollable :menu-props="() => ({ style: 'max-height: 420px' })" @select="add">
      <n-button size="small" dashed class="addb"><template #icon><n-icon :component="Plus" /></template>{{ t('me.t.add') }}</n-button>
    </n-dropdown>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { NButton, NDropdown, NIcon, NInput, NSelect } from 'naive-ui'
import { Plus, Trash, Adjustments } from '@vicons/tabler'
import ModParam from './ModParam.vue'
import { t } from '../i18n'

const props = defineProps({ modelValue: { type: Array, default: () => [] }, schema: Object, ctx: Object })
const emit = defineEmits(['update:modelValue'])
const list = computed(() => props.modelValue || [])
const more = reactive({})
const NO_DO = ['modify_damage', 'modify_block', 'modify_apply', 'play_count']
const DO = { name: 'do', kind: 'ops', required: true, default: null }
const kindOf = (tr) => (tr.template ? 'tpl:' + tr.template : 'on:' + (tr.on || ''))
function specOf(tr) {
  if (tr.template) return (props.schema.trigger_templates[tr.template] || {}).params || []
  const s = props.schema.triggers[tr.on] || []
  return NO_DO.includes(tr.on) ? s : [...s, DO]
}
const groups = (asKey) => [
  { type: 'group', label: t('me.e.tpl'), key: 'g1', children: Object.keys(props.schema.trigger_templates).map((k) => ({ [asKey]: 'tpl:' + k, label: t('me.ttpl.' + k) })) },
  { type: 'group', label: t('me.t.raw'), key: 'g2', children: Object.keys(props.schema.triggers).map((k) => ({ [asKey]: 'on:' + k, label: t('me.trg.' + k) })) },
]
const kindOptions = computed(() => groups('value'))
const addOptions = computed(() => groups('key'))
const onceOptions = computed(() => props.schema.once.map((v) => ({ value: v, label: t('me.once.' + v) })))
const shownParams = (tr, i) => specOf(tr).filter((p) => p.required || more[i] || (tr[p.name] !== undefined && tr[p.name] !== null))
function update(fn) {
  const l = JSON.parse(JSON.stringify(list.value))
  fn(l)
  emit('update:modelValue', l)
}
function fresh(k) {
  const [kind, name] = k.split(':')
  const tr = kind === 'tpl' ? { template: name } : { on: name }
  for (const p of specOf(tr)) {
    if (!p.required) continue
    tr[p.name] = p.kind === 'ops' ? [] : p.kind === 'expr' ? 1 : p.kind === 'int' ? 1 : null
  }
  return tr
}
function add(k) { update((l) => l.push(fresh(k))) }
function setKind(i, k) {
  update((l) => {
    const old = l[i]
    const tr = fresh(k)
    for (const p of specOf(tr)) if (old[p.name] !== undefined && old[p.name] !== null) tr[p.name] = old[p.name]
    for (const c of ['if', 'once', 'note']) if (old[c] !== undefined) tr[c] = old[c]
    l[i] = tr
  })
}
function setParam(i, name, v) {
  update((l) => {
    if (v === undefined || v === null || v === '') delete l[i][name]
    else l[i][name] = v
  })
}
function remove(i) { update((l) => l.splice(i, 1)) }
</script>

<style scoped>
.trs { display: flex; flex-direction: column; gap: 10px; }
.tr { border: 1px solid #34343B; border-radius: 12px; padding: 10px 12px 12px; background: #19191C; }
.th { display: flex; align-items: center; gap: 8px; }
.lbl { font-size: 12px; color: #F0A486; font-weight: 600; }
.kind { width: 260px; }
.sp { flex: 1; }
.params { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 8px; }
.mp2 { min-width: 150px; flex: 1 1 170px; }
.pl { font-size: 11.5px; color: #9C978F; margin-bottom: 4px; }
.none { font-size: 12.5px; color: #6E6A64; }
.addb { align-self: flex-start; }
</style>
