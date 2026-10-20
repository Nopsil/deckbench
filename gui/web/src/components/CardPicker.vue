<template>
  <div>
    <div class="row">
      <n-select v-model:value="pick" :options="options" filterable clearable :placeholder="placeholder"
        :render-label="renderLabel" :filter="filter" :virtual-scroll="true" style="flex:1" @update:value="add" />
      <n-checkbox v-if="pool" v-model:checked="all" size="small"><span class="muted" style="font-size:12.5px">全部卡牌</span></n-checkbox>
    </div>
    <transition-group name="fade" tag="div" class="list">
      <div v-for="(v, i) in modelValue" :key="v + i" class="item">
        <span class="rar" :class="rarCls(v)"></span>
        <span class="nm">{{ store.cardName(v) }}</span>
        <span class="id mono">{{ v.replace('+', '') }}</span>
        <n-tooltip v-if="allowUpgrade">
          <template #trigger>
            <button class="up" :class="{ on: v.endsWith('+') }" @click="toggleUp(i)">+</button>
          </template>
          {{ v.endsWith('+') ? '已升级（点击取消）' : '点击改为升级版' }}
        </n-tooltip>
        <button class="x" @click="remove(i)">×</button>
      </div>
    </transition-group>
    <div v-if="!modelValue.length" class="hint">{{ emptyText }}</div>
  </div>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { NSelect, NCheckbox, NTooltip, NTag } from 'naive-ui'
import { store } from '../api'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  pool: { type: String, default: null },
  ids: { type: Array, default: null },
  allowUpgrade: { type: Boolean, default: true },
  placeholder: { type: String, default: '搜索卡牌名或 ID…' },
  emptyText: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
const pick = ref(null)
const all = ref(false)
const RAR = { 基础: 'basic', 普通: 'common', 罕见: 'uncommon', 稀有: 'rare', 远古: 'rare', 衍生: 'token' }
const SKIP = new Set(['Deprecated', 'Status', 'Curse', 'Quest'])

const options = computed(() => {
  const cat = store.catalog
  if (!cat) return []
  let cards = cat.cards
  if (props.ids) {
    const s = new Set(props.ids)
    cards = cards.filter((c) => s.has(c.id))
  } else if (props.pool && !all.value) {
    cards = cards.filter((c) => c.pool === props.pool || c.pool === 'Colorless')
  } else {
    cards = cards.filter((c) => !SKIP.has(c.pool))
  }
  const groups = {}
  for (const c of cards) (groups[c.pool_zh] ||= []).push(c)
  return Object.entries(groups).map(([g, cs]) => ({
    type: 'group', label: g, key: g,
    children: cs.map((c) => ({ label: c.name, value: c.id, card: c })),
  }))
})
function filter(q, opt) {
  if (!opt.card) return false
  q = q.toLowerCase()
  const c = opt.card
  return c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q) || (c.up_name || '').toLowerCase().includes(q)
}
function renderLabel(opt) {
  if (!opt.card) return opt.label
  const c = opt.card
  return h('div', { style: 'display:flex;align-items:center;gap:8px;width:100%' }, [
    h('span', { style: 'font-weight:500' }, c.name),
    c.up_name ? h('span', { style: 'color:#77736C;font-size:12px' }, `→ ${c.up_name}`) : null,
    h('span', { style: 'flex:1' }),
    h(NTag, { size: 'tiny', bordered: false }, { default: () => `${c.rarity}·${c.type}` }),
    h('span', { class: 'mono', style: 'color:#6E6A64;font-size:11.5px;width:150px;text-align:right;overflow:hidden;text-overflow:ellipsis' }, c.id),
  ])
}
function add(v) {
  if (!v) return
  emit('update:modelValue', [...props.modelValue, v])
  setTimeout(() => (pick.value = null))
}
function remove(i) { const a = [...props.modelValue]; a.splice(i, 1); emit('update:modelValue', a) }
function toggleUp(i) {
  const a = [...props.modelValue]
  a[i] = a[i].endsWith('+') ? a[i].slice(0, -1) : a[i] + '+'
  emit('update:modelValue', a)
}
function rarCls(v) { const c = store.cardIndex[v.replace('+', '')]; return c ? RAR[c.rarity] || '' : '' }
</script>

<style scoped>
.list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.item { display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 6px 0 10px; border-radius: 9px; background: #25252A; border: 1px solid #323238; }
.rar { width: 8px; height: 8px; border-radius: 2px; transform: rotate(45deg); background: #8A857E; }
.rar.common { background: #B9B4AC; } .rar.uncommon { background: #7FA7C9; } .rar.rare { background: #E3B47E; } .rar.token { background: #8FBF8F; }
.nm { font-weight: 550; font-size: 13.5px; }
.id { font-size: 11px; color: #6E6A64; }
button { all: unset; cursor: pointer; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 6px; color: #8A857E; font-weight: 700; transition: all .15s; }
button:hover { background: #303036; color: #EDE9E3; }
.up.on { background: rgba(217,119,87,.2); color: #F0A486; }
</style>
