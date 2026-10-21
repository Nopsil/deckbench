<template>
  <div class="page">
    <div class="row between" style="margin-bottom:16px">
      <div class="row">
        <n-radio-group v-model:value="kind" size="small">
          <n-radio-button value="all">{{ t('hist.all') }}</n-radio-button>
          <n-radio-button value="batch">{{ t('kind.batch') }}</n-radio-button>
          <n-radio-button value="combat">{{ t('kind.combat') }}</n-radio-button>
        </n-radio-group>
        <n-input v-model:value="q" size="small" clearable :placeholder="t('hist.search')" style="width:240px"><template #prefix><n-icon :component="Search" /></template></n-input>
      </div>
      <div class="row">
        <n-button size="small" secondary :disabled="checked.length !== 2" @click="compare"><template #icon><n-icon :component="Scale" /></template>{{ t('hist.compare') }}</n-button>
        <span class="faint" style="font-size:12.5px">{{ t('hist.total', { n: rows.length }) }}</span>
      </div>
    </div>
    <div class="panel" style="padding:6px 6px">
      <n-data-table :columns="cols" :data="rows" :row-key="(r) => r.id" v-model:checked-row-keys="checked" :pagination="{ pageSize: 12 }" :bordered="false" size="medium" />
      <div v-if="!rows.length" class="empty"><div class="big">{{ t('hist.none') }}</div><div>{{ t('hist.noneHint') }}</div></div>
    </div>
    <n-modal v-model:show="renaming" preset="card" :title="t('hist.rename')" style="width:440px">
      <n-input v-model:value="newTitle" @keyup.enter="doRename" />
      <template #footer><div class="row" style="justify-content:flex-end"><n-button @click="renaming = false">{{ t('common.cancel') }}</n-button><n-button type="primary" @click="doRename">{{ t('common.save') }}</n-button></div></template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDataTable, NDropdown, NIcon, NInput, NModal, NRadioButton, NRadioGroup, NTag, useDialog, useMessage } from 'naive-ui'
import { Search, Scale, Dots } from '@vicons/tabler'
import { api, store, fmt, runTitle, STATUS } from '../api'
import { t } from '../i18n'

const router = useRouter()
const msg = useMessage()
const dialog = useDialog()
const kind = ref('all')
const q = ref('')
const checked = ref([])
const renaming = ref(false)
const newTitle = ref('')
let renameId = null

const rows = computed(() => store.runs.filter((r) => (kind.value === 'all' || r.kind === kind.value) && (!q.value || runTitle(r).includes(q.value))))
function headline(r) {
  const x = r.headline || {}
  if (r.status !== 'done') return h('span', { class: 'faint' }, r.status === 'running' ? `${r.progress?.done ?? 0} / ${r.progress?.total ?? '—'}` : '—')
  if (r.kind === 'batch') return h('div', { class: 'hl' }, [
    h('span', null, [t('hist.floor') + ' ', h('b', null, fmt.num(x.avg_floor))]), h('span', null, [t('hist.boss') + ' ', h('b', null, fmt.pct(x.boss1))]), h('span', null, [t('hist.win') + ' ', h('b', null, fmt.pct(x.win))])])
  return h('div', { class: 'hl' }, [h('span', null, [h('b', null, x.fights), ' ' + t('hist.fights')]), h('span', null, [t('hist.win') + ' ', h('b', null, fmt.pct(x.win))])])
}
const cols = [
  { type: 'selection', multiple: true, width: 44 },
  { title: () => t('hist.colTest'), key: 'title', render: (r) => h('div', { class: 'tt', onClick: () => open(r) }, [
    h('div', { class: 'tn' }, runTitle(r)),
    h('div', { class: 'ts' }, [h('span', { class: 'k ' + r.kind }, r.kind === 'batch' ? t('kind.batch') : t('kind.combat')), ' ', fmt.time(r.created), r.secs ? ` · ${fmt.secs(r.secs)}` : '',
      r.kind === 'batch' ? ` · ${t('chip.style', { style: store.styleName(r.params && r.params.style) })}` : ''])]) },
  { title: () => t('hist.colStatus'), key: 'status', width: 110, render: (r) => h(NTag, { size: 'small', bordered: false, type: STATUS[r.status]?.type }, { default: () => STATUS[r.status]?.text || r.status }) },
  { title: () => t('hist.colResult'), key: 'headline', width: 320, render: headline },
  { title: '', key: 'act', width: 170, render: (r) => h('div', { class: 'row', style: 'justify-content:flex-end' }, [
    h(NButton, { size: 'small', secondary: true, onClick: () => open(r) }, { default: () => (r.status === 'done' ? t('hist.openReport') : t('hist.view')) }),
    h(NDropdown, { trigger: 'click', options: [{ label: t('common.rerun'), key: 'rerun' }, { label: t('hist.rename'), key: 'rename' }, { label: t('common.openFolder'), key: 'folder' }, { type: 'divider' }, { label: t('common.delete'), key: 'del', props: { style: 'color:#E06C6C' } }], onSelect: (k) => act(k, r) },
      { default: () => h(NButton, { size: 'small', quaternary: true }, { icon: () => h(NIcon, { component: Dots }) }) })]) },
]
function open(r) { router.push((r.status === 'done' ? '/report/' : '/run/') + r.id) }
function compare() { router.push({ path: '/ab', query: { a: checked.value[1], b: checked.value[0] } }) }
async function act(k, r) {
  try {
    if (k === 'rerun') { const m = await api.post(`/api/runs/${r.id}/rerun`); await store.loadRuns(); router.push('/run/' + m.id) }
    if (k === 'rename') { renameId = r.id; newTitle.value = runTitle(r); renaming.value = true }
    if (k === 'folder') { const x = await api.post(`/api/runs/${r.id}/open`); if (!x.ok) msg.info(t('common.resultFolder') + x.path) }
    if (k === 'del') dialog.warning({ title: t('hist.delQ'), content: t('hist.delHint'), positiveText: t('common.delete'), negativeText: t('common.cancel'),
      onPositiveClick: async () => { await api.del('/api/runs/' + r.id); await store.loadRuns(); msg.success(t('common.deleted')) } })
  } catch (e) { msg.error(e.message) }
}
async function doRename() { await api.patch('/api/runs/' + renameId, { title: newTitle.value }); renaming.value = false; store.loadRuns() }
</script>

<style scoped>
:deep(.tt) { cursor: pointer; padding: 4px 0; }
:deep(.tn) { font-weight: 600; font-size: 14px; }
:deep(.tt:hover .tn) { color: #F0A486; }
:deep(.ts) { font-size: 12px; color: #77736C; margin-top: 4px; }
:deep(.k) { padding: 1px 7px; border-radius: 5px; font-size: 11.5px; }
:deep(.k.batch) { background: rgba(217,119,87,.14); color: #F0A486; }
:deep(.k.combat) { background: rgba(127,167,201,.14); color: #9DC0DE; }
:deep(.hl) { display: flex; gap: 16px; font-size: 13px; color: #8A857E; }
:deep(.hl b) { color: #EDE9E3; font-weight: 650; }
</style>
