<template>
  <div class="mp" :class="{ wide: spec.kind === 'ops' || spec.kind === 'expr' && wideExpr }">
    <div class="pl">{{ label }}<span v-if="spec.required" class="req">*</span></div>
    <template v-if="spec.kind === 'ops'">
      <mod-effects :model-value="modelValue || []" :schema="schema" :ctx="ctx" :depth="depth + 1" @update:model-value="emit('update:modelValue', $event)" />
    </template>
    <n-select v-else-if="spec.kind === 'power'" size="small" filterable tag :value="modelValue ?? null" :options="ctx.powerOptions" :placeholder="defText" clearable @update:value="emit('update:modelValue', $event)" />
    <n-select v-else-if="spec.kind === 'card'" size="small" filterable tag :value="modelValue ?? null" :options="ctx.cardOptions" :placeholder="defText" clearable @update:value="emit('update:modelValue', $event)" />
    <n-select v-else-if="spec.kind === 'target'" size="small" :value="modelValue ?? null" :options="targetOptions" :placeholder="defLabel" clearable @update:value="emit('update:modelValue', $event)" />
    <n-select v-else-if="spec.kind.startsWith('choice:')" size="small" :value="modelValue ?? null" :options="choiceOptions" :placeholder="defLabel" clearable @update:value="emit('update:modelValue', $event)" />
    <n-switch v-else-if="spec.kind === 'bool'" size="small" :value="!!modelValue" @update:value="emit('update:modelValue', $event || undefined)" />
    <n-input-number v-else-if="spec.kind === 'int'" size="small" :value="modelValue ?? null" :placeholder="defText" clearable @update:value="emit('update:modelValue', $event ?? undefined)" />
    <n-input v-else size="small" :value="modelValue === undefined || modelValue === null ? '' : String(modelValue)" :placeholder="defText"
             :class="{ mono: spec.kind === 'expr' }" :title="spec.kind === 'expr' ? t('me.e.exprHint') : ''" @update:value="onText" />
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent } from 'vue'
import { NInput, NInputNumber, NSelect, NSwitch } from 'naive-ui'
import { t, has } from '../i18n'

const ModEffects = defineAsyncComponent(() => import('./ModEffects.vue'))
const props = defineProps({ spec: Object, modelValue: null, schema: Object, ctx: Object, depth: { type: Number, default: 0 } })
const emit = defineEmits(['update:modelValue'])
const label = computed(() => (has('me.par.' + props.spec.name) ? t('me.par.' + props.spec.name) : props.spec.name))
const lab = (prefix, v) => (has(prefix + v) ? t(prefix + v) : v)
const targetOptions = computed(() => props.schema.target_specs.map((v) => ({ value: v, label: lab('me.ts.', v) })))
const choiceOptions = computed(() => props.spec.kind.slice(7).split('|').map((v) => ({ value: v, label: lab('me.ch.', v) })))
const defText = computed(() => (props.spec.default === null || props.spec.default === undefined ? '' : String(props.spec.default)))
const defLabel = computed(() => {
  const d = props.spec.default
  if (d === null || d === undefined) return ''
  return props.spec.kind === 'target' ? lab('me.ts.', d) : lab('me.ch.', d)
})
const wideExpr = computed(() => typeof props.modelValue === 'string' && props.modelValue.length > 28)
function onText(v) {
  if (v === '') return emit('update:modelValue', undefined)
  if (props.spec.kind === 'expr' && /^-?\d+(\.\d+)?$/.test(v.trim())) return emit('update:modelValue', Number(v))
  emit('update:modelValue', v)
}
</script>

<style scoped>
.mp { min-width: 150px; flex: 1 1 170px; }
.mp.wide { flex-basis: 100%; }
.pl { font-size: 11.5px; color: #9C978F; margin-bottom: 4px; }
.req { color: #E58A68; margin-left: 2px; }
</style>
