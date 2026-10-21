<template>
  <div class="effs" :class="'d' + Math.min(depth, 3)">
    <div v-if="!list.length" class="none">{{ t('me.e.empty') }}</div>
    <div v-for="(e, i) in list" :key="i" class="eff">
      <div class="eh">
        <span class="num">{{ i + 1 }}</span>
        <n-select size="small" class="kind" :value="kindOf(e)" :options="kindOptions" filterable @update:value="(k) => setKind(i, k)" />
        <div class="sp"></div>
        <n-button quaternary size="tiny" :title="t('me.e.more')" @click="toggleMore(i)"><template #icon><n-icon :component="Adjustments" /></template></n-button>
        <n-button quaternary size="tiny" :disabled="i === 0" @click="move(i, -1)"><template #icon><n-icon :component="ArrowUp" /></template></n-button>
        <n-button quaternary size="tiny" :disabled="i === list.length - 1" @click="move(i, 1)"><template #icon><n-icon :component="ArrowDown" /></template></n-button>
        <n-button quaternary size="tiny" @click="remove(i)"><template #icon><n-icon :component="Trash" /></template></n-button>
      </div>
      <div class="params">
        <mod-param v-for="p in shownParams(e, i)" :key="p.name" :spec="p" :model-value="e[p.name]" :schema="schema" :ctx="ctx" :depth="depth"
                   @update:model-value="(v) => setParam(i, p.name, v)" />
        <template v-if="more[i] || e.if || e.once">
          <div class="mp2">
            <div class="pl">{{ t('me.e.if') }}</div>
            <n-input size="small" class="mono" :value="e.if || ''" :placeholder="t('me.e.ifPh')" @update:value="(v) => setParam(i, 'if', v || undefined)" />
          </div>
          <div class="mp2">
            <div class="pl">{{ t('me.e.once') }}</div>
            <n-select size="small" :value="e.once || null" :options="onceOptions" clearable :placeholder="t('me.e.onceNone')" @update:value="(v) => setParam(i, 'once', v || undefined)" />
          </div>
        </template>
      </div>
    </div>
    <n-dropdown trigger="click" :options="addOptions" scrollable :menu-props="() => ({ style: 'max-height: 420px' })" @select="add">
      <n-button size="small" dashed class="addb"><template #icon><n-icon :component="Plus" /></template>{{ t('me.e.add') }}</n-button>
    </n-dropdown>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { NButton, NDropdown, NIcon, NInput, NSelect } from 'naive-ui'
import { Plus, Trash, ArrowUp, ArrowDown, Adjustments } from '@vicons/tabler'
import ModParam from './ModParam.vue'
import { t } from '../i18n'

const props = defineProps({ modelValue: { type: Array, default: () => [] }, schema: Object, ctx: Object, depth: { type: Number, default: 0 } })
const emit = defineEmits(['update:modelValue'])
const list = computed(() => props.modelValue || [])
const more = reactive({})
const kindOf = (e) => (e.template ? 'tpl:' + e.template : 'op:' + (e.op || ''))
const specOf = (e) => (e.template ? props.schema.templates[e.template] : props.schema.ops[e.op]) || []
const kindOptions = computed(() => [
  { type: 'group', label: t('me.e.basic'), key: 'g1', children: Object.keys(props.schema.ops).map((k) => ({ value: 'op:' + k, label: t('me.op.' + k) })) },
  { type: 'group', label: t('me.e.tpl'), key: 'g2', children: Object.keys(props.schema.templates).map((k) => ({ value: 'tpl:' + k, label: t('me.tpl.' + k) })) },
])
const addOptions = computed(() => [
  { type: 'group', label: t('me.e.basic'), key: 'g1', children: Object.keys(props.schema.ops).map((k) => ({ key: 'op:' + k, label: t('me.op.' + k) })) },
  { type: 'group', label: t('me.e.tpl'), key: 'g2', children: Object.keys(props.schema.templates).map((k) => ({ key: 'tpl:' + k, label: t('me.tpl.' + k) })) },
])
const onceOptions = computed(() => props.schema.once.map((v) => ({ value: v, label: t('me.once.' + v) })))
function shownParams(e, i) {
  return specOf(e).filter((p) => p.required || more[i] || (e[p.name] !== undefined && e[p.name] !== null))
}
function update(fn) {
  const l = JSON.parse(JSON.stringify(list.value))
  fn(l)
  emit('update:modelValue', l)
}
function fresh(k) {
  const [kind, name] = k.split(':')
  const e = kind === 'tpl' ? { template: name } : { op: name }
  const spec = kind === 'tpl' ? props.schema.templates[name] : props.schema.ops[name]
  for (const p of spec || []) {
    if (!p.required) continue
    if (p.kind === 'ops') e[p.name] = []
    else if (p.kind === 'expr') e[p.name] = p.name === 'cond' ? 'True' : 1
    else e[p.name] = null
  }
  return e
}
function add(k) { update((l) => l.push(fresh(k))) }
function setKind(i, k) {
  update((l) => {
    const old = l[i]
    const e = fresh(k)
    for (const p of specOf(e)) if (old[p.name] !== undefined && old[p.name] !== null) e[p.name] = old[p.name]
    for (const c of ['if', 'once', 'note']) if (old[c] !== undefined) e[c] = old[c]
    l[i] = e
  })
}
function setParam(i, name, v) {
  update((l) => {
    if (v === undefined || v === null || v === '') delete l[i][name]
    else l[i][name] = v
  })
}
function move(i, d) { update((l) => { const [x] = l.splice(i, 1); l.splice(i + d, 0, x) }) }
function remove(i) { update((l) => l.splice(i, 1)) }
function toggleMore(i) { more[i] = !more[i] }
</script>

<style scoped>
.effs { display: flex; flex-direction: column; gap: 8px; }
.eff { border: 1px solid #2E2E34; border-radius: 10px; padding: 8px 10px 10px; background: #19191C; }
.d1 .eff { background: #1E1E22; }
.d2 .eff, .d3 .eff { background: #222227; }
.eh { display: flex; align-items: center; gap: 6px; }
.num { width: 20px; height: 20px; border-radius: 6px; background: #2A2A30; color: #B9B4AC; font-size: 11.5px; display: grid; place-items: center; flex: none; }
.kind { width: 230px; }
.sp { flex: 1; }
.params { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 8px; }
.params:empty { display: none; }
.mp2 { min-width: 150px; flex: 1 1 170px; }
.pl { font-size: 11.5px; color: #9C978F; margin-bottom: 4px; }
.none { font-size: 12.5px; color: #6E6A64; }
.addb { align-self: flex-start; }
</style>
