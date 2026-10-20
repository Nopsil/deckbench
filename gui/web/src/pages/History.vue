<template>
  <div class="page">
    <div class="row between" style="margin-bottom:16px">
      <div class="row">
        <n-radio-group v-model:value="kind" size="small">
          <n-radio-button value="all">全部</n-radio-button>
          <n-radio-button value="batch">整局批量</n-radio-button>
          <n-radio-button value="combat">战斗实验</n-radio-button>
        </n-radio-group>
        <n-input v-model:value="q" size="small" clearable placeholder="搜索标题…" style="width:240px"><template #prefix><n-icon :component="Search" /></template></n-input>
      </div>
      <div class="row">
        <n-button size="small" secondary :disabled="checked.length !== 2" @click="compare"><template #icon><n-icon :component="Scale" /></template>对比选中的两次</n-button>
        <span class="faint" style="font-size:12.5px">共 {{ rows.length }} 次</span>
      </div>
    </div>
    <div class="panel" style="padding:6px 6px">
      <n-data-table :columns="cols" :data="rows" :row-key="(r) => r.id" v-model:checked-row-keys="checked" :pagination="{ pageSize: 12 }" :bordered="false" size="medium" />
      <div v-if="!rows.length" class="empty"><div class="big">还没有记录</div><div>每次运行都会自动保存在这里。</div></div>
    </div>
    <n-modal v-model:show="renaming" preset="card" title="重命名" style="width:440px">
      <n-input v-model:value="newTitle" @keyup.enter="doRename" />
      <template #footer><div class="row" style="justify-content:flex-end"><n-button @click="renaming = false">取消</n-button><n-button type="primary" @click="doRename">保存</n-button></div></template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDataTable, NDropdown, NIcon, NInput, NModal, NRadioButton, NRadioGroup, NTag, useDialog, useMessage } from 'naive-ui'
import { Search, Scale, Dots } from '@vicons/tabler'
import { api, store, fmt, runTitle, STATUS } from '../api'

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
    h('span', null, ['层数 ', h('b', null, fmt.num(x.avg_floor))]), h('span', null, ['首领 ', h('b', null, fmt.pct(x.boss1))]), h('span', null, ['胜率 ', h('b', null, fmt.pct(x.win))])])
  return h('div', { class: 'hl' }, [h('span', null, [h('b', null, x.fights), ' 场']), h('span', null, ['胜率 ', h('b', null, fmt.pct(x.win))])])
}
const cols = [
  { type: 'selection', multiple: true, width: 44 },
  { title: '测试', key: 'title', render: (r) => h('div', { class: 'tt', onClick: () => open(r) }, [
    h('div', { class: 'tn' }, runTitle(r)),
    h('div', { class: 'ts' }, [h('span', { class: 'k ' + r.kind }, r.kind === 'batch' ? '整局批量' : '战斗实验'), ' ', fmt.time(r.created), r.secs ? ` · ${fmt.secs(r.secs)}` : ''])]) },
  { title: '状态', key: 'status', width: 96, render: (r) => h(NTag, { size: 'small', bordered: false, type: STATUS[r.status]?.type }, { default: () => STATUS[r.status]?.text || r.status }) },
  { title: '结果', key: 'headline', width: 300, render: headline },
  { title: '', key: 'act', width: 170, render: (r) => h('div', { class: 'row', style: 'justify-content:flex-end' }, [
    h(NButton, { size: 'small', secondary: true, onClick: () => open(r) }, { default: () => (r.status === 'done' ? '打开报告' : '查看') }),
    h(NDropdown, { trigger: 'click', options: [{ label: '再跑一次', key: 'rerun' }, { label: '重命名', key: 'rename' }, { label: '打开文件夹', key: 'folder' }, { type: 'divider' }, { label: '删除', key: 'del', props: { style: 'color:#E06C6C' } }], onSelect: (k) => act(k, r) },
      { default: () => h(NButton, { size: 'small', quaternary: true }, { icon: () => h(NIcon, { component: Dots }) }) })]) },
]
function open(r) { router.push((r.status === 'done' ? '/report/' : '/run/') + r.id) }
function compare() { router.push({ path: '/ab', query: { a: checked.value[1], b: checked.value[0] } }) }
async function act(k, r) {
  try {
    if (k === 'rerun') { const m = await api.post(`/api/runs/${r.id}/rerun`); await store.loadRuns(); router.push('/run/' + m.id) }
    if (k === 'rename') { renameId = r.id; newTitle.value = runTitle(r); renaming.value = true }
    if (k === 'folder') { const x = await api.post(`/api/runs/${r.id}/open`); if (!x.ok) msg.info('结果文件夹：' + x.path) }
    if (k === 'del') dialog.warning({ title: '删除这次测试？', content: '结果文件会一起删除，无法恢复。', positiveText: '删除', negativeText: '取消',
      onPositiveClick: async () => { await api.del('/api/runs/' + r.id); await store.loadRuns(); msg.success('已删除') } })
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
