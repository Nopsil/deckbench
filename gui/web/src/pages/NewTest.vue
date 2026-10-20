<template>
  <div class="page">
    <div v-if="!cat" class="panel empty">
      <n-spin v-if="!store.catalogError" /><div class="big" style="margin-top:12px">{{ store.catalogError ? '载入失败：' + store.catalogError : '正在载入卡牌和角色数据…' }}</div>
    </div>
    <div v-else class="layout">
      <div class="form">
        <div class="modes">
          <button class="mode" :class="{ on: kind === 'batch' }" @click="kind = 'batch'">
            <n-icon :component="Route" size="22" />
            <div><div class="mt">整局批量</div><div class="ms">从第 1 层打到通关，统计层数、首领到达率、胜率</div></div>
          </button>
          <button class="mode" :class="{ on: kind === 'combat' }" @click="kind = 'combat'">
            <n-icon :component="Swords" size="22" />
            <div><div class="mt">战斗实验</div><div class="ms">固定卡组打普通/精英/首领，统计单场胜率与掉血</div></div>
          </button>
        </div>

        <template v-if="kind === 'batch'">
          <div class="panel">
            <h3>角色与难度</h3>
            <div class="chars">
              <button v-for="c in cat.characters" :key="c.id" class="char" :class="{ on: b.char === c.id }" @click="setChar(c.id)">
                <span class="av" :style="{ background: charColor(c.id) }">{{ c.name.slice(0, 1) }}</span>
                <span class="cn">{{ c.name }}</span>
                <span class="ci mono">{{ c.id }}</span>
              </button>
            </div>
            <div class="label" style="margin-top:20px">进阶等级 <b class="accent">A{{ b.asc }}</b></div>
            <n-slider v-model:value="b.asc" :min="0" :max="10" :step="1" :marks="{ 0: 'A0', 5: 'A5', 10: 'A10' }" />
          </div>

          <div class="panel">
            <h3>规模</h3>
            <div class="grid" style="grid-template-columns: 1.25fr 1fr 1fr">
              <div>
                <div class="label">局数</div>
                <n-input-number v-model:value="b.n" :min="1" :max="5000" style="width:100%" />
                <div class="quick"><button v-for="q in [20, 100, 400, 1000]" :key="q" :class="{ on: b.n === q }" @click="b.n = q">{{ q }}</button></div>
              </div>
              <div>
                <div class="label">起始种子</div>
                <n-input-number v-model:value="b.start" :min="0" style="width:100%"><template #prefix><span class="faint">R</span></template></n-input-number>
                <div class="hint">种子 R{{ b.start }} … R{{ b.start + b.n - 1 }}；A/B 两组用同一批种子才能配对。</div>
              </div>
              <div>
                <div class="label">并行进程 <b class="accent">{{ b.procs }}</b><span class="faint"> / {{ cat.cpu }} 核</span></div>
                <n-slider v-model:value="b.procs" :min="1" :max="cat.cpu" :step="1" />
              </div>
            </div>
          </div>

          <div class="panel">
            <h3>AI</h3>
            <div class="agents">
              <button v-for="a in cat.agents_batch" :key="a.id" class="agent" :class="{ on: b.agent === a.id }" @click="b.agent = a.id">
                <div class="an">{{ a.name }}</div><div class="ad">{{ a.desc }}</div>
              </button>
            </div>
          </div>

          <div v-if="b.char === 'Claude'" class="panel">
            <h3>Claude娘 变体 <span class="faint" style="font-weight:400;font-size:12.5px">（可多选，按顺序叠加；不选 = 当前设计 v3.5.1）</span></h3>
            <n-select v-model:value="b.variants" multiple filterable :options="variantOptions" :render-label="variantLabel" placeholder="不使用变体" />
          </div>

          <div class="panel">
            <h3>起始牌组调整 <span class="faint" style="font-weight:400;font-size:12.5px">（单卡 A/B 用：在进入第一幕前改牌组，地图和遭遇序列不变）</span></h3>
            <div class="grid g2">
              <div>
                <div class="label">强制加入</div>
                <card-picker v-model="b.force" :pool="b.char" empty-text="不加牌。点「+」可改成升级版。" />
              </div>
              <div>
                <div class="label">移除（各移除 1 张）</div>
                <card-picker v-model="b.replace" :ids="starterIds" :allow-upgrade="false" placeholder="从起始牌组里选…" empty-text="不移除。只能选起始牌组里的牌。" />
                <div class="hint">起始牌组：{{ starterText }}</div>
              </div>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="panel">
            <h3>实验来源</h3>
            <n-radio-group v-model:value="c.source">
              <n-radio-button value="preset">预设实验</n-radio-button>
              <n-radio-button value="custom">自定义</n-radio-button>
            </n-radio-group>
            <div v-if="c.source === 'preset'" style="margin-top:14px">
              <n-select v-model:value="c.preset" :options="presetOptions" @update:value="applyPreset" />
              <div v-if="preset" class="pinfo">
                <span class="chip">{{ preset.decks.length }} 个卡组</span>
                <span class="chip">房间：{{ preset.rooms.join('、') }}</span>
                <span class="chip">mod：{{ preset.mods.join('、') }}</span>
                <span v-if="preset.n_extra" class="chip">循环探针 {{ preset.n_extra }} 组</span>
                <span class="chip">默认每格 {{ preset.fights }} 场</span>
              </div>
            </div>
          </div>

          <div v-if="c.source === 'custom'" class="panel">
            <h3>Mod 与卡组</h3>
            <div class="label">Mod</div>
            <n-checkbox-group v-model:value="c.mods" @update:value="onMods">
              <div class="mods">
                <n-checkbox v-for="m in cat.mods" :key="m.id" :value="m.id">
                  <span>{{ m.title }}</span> <span class="faint mono" style="font-size:11.5px">{{ m.id }}</span>
                  <n-tag v-if="m.user" size="tiny" type="primary" :bordered="false" style="margin-left:6px">上传</n-tag>
                </n-checkbox>
              </div>
            </n-checkbox-group>
            <div class="label" style="margin-top:16px">卡组 <span class="faint">（已选 {{ c.decks.length }}）</span></div>
            <div v-if="!deckGroups.length" class="hint">先选 mod。</div>
            <div v-for="g in deckGroups" :key="g.mod" class="dg">
              <div class="row between"><div class="dgt">{{ g.title }}</div>
                <div class="row"><n-button text size="tiny" @click="selDecks(g, 'start')">只选起始</n-button><n-button text size="tiny" @click="selDecks(g, 'all')">全选</n-button><n-button text size="tiny" @click="selDecks(g, 'none')">清空</n-button></div></div>
              <n-checkbox-group v-model:value="c.decks">
                <div class="decks">
                  <n-checkbox v-for="d in g.decks" :key="d.id" :value="d.id" :label="d.name" />
                </div>
              </n-checkbox-group>
            </div>
            <div class="grid g2" style="margin-top:16px">
              <div><div class="label">房间</div>
                <n-checkbox-group v-model:value="c.rooms"><div class="row"><n-checkbox v-for="r in cat.rooms" :key="r" :value="r" :label="r" /></div></n-checkbox-group></div>
              <div><div class="label">每场回合上限</div><n-input-number v-model:value="c.max_turns" :min="1" :max="200" /></div>
            </div>
          </div>

          <div class="panel">
            <h3>规模与 AI</h3>
            <div class="grid g4">
              <div><div class="label">每格场数</div><n-input-number v-model:value="c.fights" :min="1" :max="5000" /></div>
              <div><div class="label">种子</div><n-input-number v-model:value="c.seed" :min="0" /></div>
              <div><div class="label">AI</div><n-select v-model:value="c.agent" :options="cat.agents_combat.map(a => ({ label: a.name, value: a.id }))" /></div>
              <div><div class="label">并行 <b class="accent">{{ c.procs }}</b></div><n-slider v-model:value="c.procs" :min="1" :max="cat.cpu" /></div>
            </div>
          </div>

          <div class="panel">
            <div class="row between"><h3 style="margin:0">上传 mod</h3>
              <n-upload :custom-request="upload" :show-file-list="false" accept=".zip">
                <n-button size="small" secondary :loading="uploading">选择 zip…</n-button>
              </n-upload></div>
            <div class="hint" style="margin-top:8px">zip 里放 <span class="mono">mod.yaml</span> + 卡表/卡组 YAML（+ 可选 hooks.py），格式同仓库 README「给新 mod 写内容」。上传后会用模拟器试加载一遍，通过才会加入上面的 mod 列表。只用于战斗实验；整局批量目前只支持内置的 Claude娘 v3.5。hooks.py 是会被执行的 Python 代码，只上传你信任的 mod。</div>
            <div v-if="userMods.length" class="umods">
              <div v-for="m in userMods" :key="m.id" class="umod">
                <n-icon :component="Package" size="18" class="accent" />
                <div style="flex:1"><div style="font-weight:600">{{ m.title }}</div><div class="faint" style="font-size:12px">{{ m.id }} · {{ m.decks.length }} 个卡组{{ m.deps.length ? ' · 依赖 ' + m.deps.join('、') : '' }}</div></div>
                <n-popconfirm @positive-click="delMod(m.id)"><template #trigger><n-button text size="small">删除</n-button></template>删除这个上传的 mod？</n-popconfirm>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="aside">
        <div class="panel sticky">
          <div class="sec-title">本次测试</div>
          <n-input v-model:value="title" :placeholder="autoTitle" />
          <div class="sum">
            <template v-if="kind === 'batch'">
              <div><span>模式</span><b>整局批量</b></div>
              <div><span>角色</span><b>{{ store.charName(b.char) }}</b></div>
              <div><span>进阶</span><b>A{{ b.asc }}</b></div>
              <div><span>局数</span><b>{{ b.n }}</b></div>
              <div><span>AI</span><b>{{ store.agentName('batch', b.agent) }}</b></div>
              <div v-if="b.char === 'Claude'"><span>变体</span><b>{{ b.variants.length ? b.variants.join(' + ') : '无' }}</b></div>
              <div><span>加入</span><b>{{ b.force.length ? b.force.map(store.cardName).join('、') : '—' }}</b></div>
              <div><span>移除</span><b>{{ b.replace.length ? b.replace.map(store.cardName).join('、') : '—' }}</b></div>
            </template>
            <template v-else>
              <div><span>模式</span><b>战斗实验</b></div>
              <div><span>来源</span><b>{{ c.source === 'preset' ? (preset && preset.title) : '自定义' }}</b></div>
              <div v-if="c.source === 'custom'"><span>卡组</span><b>{{ c.decks.length }} 个</b></div>
              <div><span>每格</span><b>{{ c.fights }} 场</b></div>
              <div><span>AI</span><b>{{ store.agentName('combat', c.agent) }}</b></div>
              <div v-if="c.source === 'custom'"><span>预计总场数</span><b>{{ combatTotal }}</b></div>
            </template>
          </div>
          <n-button type="primary" size="large" block :loading="starting" :disabled="!canStart" @click="start">
            <template #icon><n-icon :component="PlayerPlay" /></template>开始运行
          </n-button>
          <div class="hint" style="text-align:center">运行后会显示实时速度和预计剩余时间</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, h, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCheckbox, NCheckboxGroup, NIcon, NInput, NInputNumber, NPopconfirm, NRadioButton, NRadioGroup, NSelect, NSlider, NSpin, NTag, NUpload, useMessage } from 'naive-ui'
import { Route, Bolt as Swords, PlayerPlay, Package } from '@vicons/tabler'
import CardPicker from '../components/CardPicker.vue'
import { api, store, runTitle } from '../api'

const router = useRouter()
const msg = useMessage()
watch(() => store.catalog, (v) => { if (v) fetch('/api/clientlog', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ level: 'info', msg: 'newtest catalog ready' }) }).catch(() => {}) }, { immediate: true })
const cat = computed(() => store.catalog)
const kind = ref(localStorage.getItem('nt.kind') || 'batch')
const title = ref('')
const starting = ref(false)
const uploading = ref(false)
const saved = JSON.parse(localStorage.getItem('nt.form') || '{}')
const b = reactive({ char: 'Ironclad', asc: 0, n: 100, start: 0, procs: 4, agent: 'heuristic', variants: [], force: [], replace: [], ...(saved.b || {}) })
const c = reactive({ source: 'preset', preset: 'quick', mods: ['vanilla'], decks: [], rooms: ['普通', '精英', '首领'], max_turns: 30, fights: 20, seed: 1, agent: 'heuristic', procs: 4, ...(saved.c || {}) })
watch([b, c, kind], () => {
  localStorage.setItem('nt.form', JSON.stringify({ b, c }))
  localStorage.setItem('nt.kind', kind.value)
}, { deep: true })
watch(cat, (v) => {
  if (!v) return
  if (!saved.b) b.procs = v.cpu
  if (!saved.c) c.procs = v.cpu
  if (!v.mods.find((m) => m.id === 'vanilla')) c.mods = []
  c.mods = c.mods.filter((x) => v.mods.find((m) => m.id === x))
}, { immediate: true })

const CHAR_COLORS = { Ironclad: '#C4574A', Silent: '#6FA36B', Defect: '#5E8FC4', Necrobinder: '#9A7CC9', Regent: '#D6A54A', Claude: '#D97757' }
const charColor = (id) => CHAR_COLORS[id] || '#77736C'
function setChar(id) { b.char = id; b.replace = []; if (id !== 'Claude') b.variants = [] }
const starterIds = computed(() => [...new Set((cat.value?.starters?.[b.char]) || [])])
const starterText = computed(() => {
  const l = cat.value?.starters?.[b.char] || []
  const cnt = {}
  for (const x of l) cnt[x] = (cnt[x] || 0) + 1
  return Object.entries(cnt).map(([k, n]) => store.cardName(k) + (n > 1 ? '×' + n : '')).join('、')
})
const variantOptions = computed(() => (cat.value?.variants || []).map((v) => ({ label: v.id, value: v.id, v })))
const variantLabel = (o) => h('div', { style: 'display:flex;gap:10px;align-items:baseline' }, [
  h('span', { class: 'mono', style: 'font-weight:600' }, o.v.id), h('span', { style: 'color:#8A857E;font-size:12.5px' }, o.v.desc || o.v.detail)])

const presetOptions = computed(() => (cat.value?.experiments || []).map((e) => ({ label: `${e.title}（${e.id}）`, value: e.id })))
const preset = computed(() => (cat.value?.experiments || []).find((e) => e.id === c.preset))
function applyPreset() { if (preset.value) { c.fights = preset.value.fights; c.seed = preset.value.seed; c.agent = preset.value.agent } }
const userMods = computed(() => (cat.value?.mods || []).filter((m) => m.user))
function onMods(v) {
  const add = new Set(v)
  for (const id of v) { const m = cat.value.mods.find((x) => x.id === id); (m?.deps || []).forEach((d) => add.add(d)) }
  const order = cat.value.mods.map((m) => m.id).filter((x) => add.has(x))
  c.mods = order
  const ok = new Set(deckGroups.value.flatMap((g) => g.decks.map((d) => d.id)))
  c.decks = c.decks.filter((d) => ok.has(d))
}
const deckGroups = computed(() => (cat.value?.mods || []).filter((m) => c.mods.includes(m.id)).map((m) => ({ mod: m.id, title: m.title, decks: m.decks.filter((d) => !String(d.stage).includes('探针')) })))
function selDecks(g, how) {
  const ids = g.decks.map((d) => d.id)
  let rest = c.decks.filter((x) => !ids.includes(x))
  if (how === 'all') rest = rest.concat(ids)
  if (how === 'start') rest = rest.concat(g.decks.filter((d) => String(d.stage).includes('起始')).map((d) => d.id))
  c.decks = rest
}
const combatTotal = computed(() => {
  let n = 0
  for (const g of deckGroups.value) for (const d of g.decks) if (c.decks.includes(d.id)) n += (d.acts || [1]).length * c.rooms.length * c.fights
  return n
})
const autoTitle = computed(() => (kind.value === 'batch' ? runTitle({ kind: 'batch', params: { ...b } }) : (c.source === 'preset' ? (preset.value?.title || '') : '自定义战斗实验')))
const canStart = computed(() => kind.value === 'batch' ? b.n > 0 : (c.source === 'preset' ? !!c.preset : c.decks.length > 0 && c.rooms.length > 0))

async function start() {
  starting.value = true
  try {
    let params
    if (kind.value === 'batch') params = { char: b.char, asc: b.asc, n: b.n, start: b.start, procs: b.procs, agent: b.agent, variants: b.char === 'Claude' ? b.variants : [], force: b.force, replace: b.replace }
    else if (c.source === 'preset') params = { preset: c.preset, fights: c.fights, seed: c.seed, agent: c.agent, procs: c.procs }
    else params = { mods: c.mods, decks: c.decks, rooms: c.rooms, max_turns: c.max_turns, fights: c.fights, seed: c.seed, agent: c.agent, procs: c.procs }
    const m = await api.post('/api/runs', { kind: kind.value, params, title: title.value || autoTitle.value })
    store.loadRuns()
    router.push('/run/' + m.id)
  } catch (e) { msg.error(e.message) } finally { starting.value = false }
}
async function upload({ file, onFinish, onError }) {
  uploading.value = true
  const fd = new FormData()
  fd.append('file', file.file)
  try {
    const r = await api.upload('/api/mods/upload', fd)
    msg.success(`已加入 mod「${r.title}」：${r.decks} 个卡组可用` + (r.deps.length ? `（需要和 ${r.deps.join('、')} 一起加载）` : ''))
    await store.loadCatalog()
    kind.value = 'combat'; c.source = 'custom'
    onMods([...c.mods, r.name])
    onFinish()
  } catch (e) { msg.error(e.message, { duration: 8000 }); onError() } finally { uploading.value = false }
}
async function delMod(id) {
  try { await api.del('/api/mods/' + id); c.mods = c.mods.filter((x) => x !== id); await store.loadCatalog(); msg.success('已删除') } catch (e) { msg.error(e.message) }
}
</script>

<style scoped>
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 20px; align-items: start; }
.aside .sticky { position: sticky; top: 16px; }
.modes { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
.mode { all: unset; cursor: pointer; display: flex; gap: 14px; align-items: flex-start; padding: 18px 20px; border-radius: 14px; border: 1px solid #2E2E34; background: #1B1B1F; color: #9C978F; transition: all .18s; }
.mode:hover { border-color: #3C3C43; color: #CFCAC2; }
.mode.on { border-color: rgba(217,119,87,.6); background: linear-gradient(150deg, rgba(217,119,87,.15), #1E1E22 65%); color: #F0A486; box-shadow: 0 0 0 3px rgba(217,119,87,.08); }
.mt { font-weight: 700; font-size: 15.5px; color: #EDE9E3; }
.ms { font-size: 12.5px; margin-top: 5px; color: #8A857E; line-height: 1.5; }
.chars { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
.char { all: unset; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 6px 12px; border-radius: 12px; border: 1px solid #2E2E34; background: #1A1A1E; transition: all .16s; }
.char:hover { border-color: #3C3C43; transform: translateY(-1px); }
.char.on { border-color: #D97757; background: rgba(217,119,87,.1); }
.av { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; color: #17171A; font-weight: 800; font-size: 16px; }
.cn { font-size: 13.5px; font-weight: 600; }
.ci { font-size: 10.5px; color: #6E6A64; }
.accent { color: #F0A486; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.quick button { all: unset; cursor: pointer; padding: 2px 8px; border-radius: 7px; font-size: 12.5px; background: #25252A; color: #A9A49C; border: 1px solid #2E2E34; }
.quick button:hover { color: #EDE9E3; }
.quick button.on { background: rgba(217,119,87,.16); color: #F0A486; border-color: rgba(217,119,87,.4); }
.agents { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.agent { all: unset; cursor: pointer; padding: 12px 14px; border-radius: 11px; border: 1px solid #2E2E34; background: #1A1A1E; transition: all .16s; }
.agent:hover { border-color: #3C3C43; }
.agent.on { border-color: #D97757; background: rgba(217,119,87,.1); }
.an { font-weight: 650; font-size: 13.5px; }
.ad { font-size: 12px; color: #8A857E; margin-top: 4px; line-height: 1.45; }
.pinfo { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.mods { display: flex; flex-wrap: wrap; gap: 10px 22px; }
.dg { margin-top: 10px; padding: 12px 14px; border-radius: 11px; background: #1A1A1E; border: 1px solid #2A2A2F; }
.dgt { font-weight: 600; font-size: 13px; color: #CFCAC2; margin-bottom: 8px; }
.decks { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px 14px; }
.sum { margin: 16px 0 18px; display: flex; flex-direction: column; gap: 9px; }
.sum > div { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
.sum span { color: #8A857E; flex: none; }
.sum b { font-weight: 550; text-align: right; color: #E4DFD8; word-break: break-all; }
.umods { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
.umod { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 10px; background: #1A1A1E; border: 1px solid #2A2A2F; }
</style>
