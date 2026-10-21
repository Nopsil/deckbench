<template>
  <div class="page">
    <div class="panel bar">
      <div class="row wrap">
        <n-select class="opener" :value="openId" :options="modOptions" filterable :placeholder="t('me.openPh')" :render-label="modLabel" @update:value="openMod" />
        <n-button @click="newMod"><template #icon><n-icon :component="FilePlus" /></template>{{ t('me.new') }}</n-button>
        <n-button @click="$refs.zip.click()"><template #icon><n-icon :component="FileImport" /></template>{{ t('me.import') }}</n-button>
        <input ref="zip" type="file" accept=".zip" style="display:none" @change="importZip" />
        <n-button :disabled="!savedName" tag="a" :href="savedName ? '/api/modeditor/export/' + savedName : undefined"><template #icon><n-icon :component="FileExport" /></template>{{ t('me.export') }}</n-button>
        <div class="sp"></div>
        <span v-if="mod && dirty" class="chip acc">{{ t('me.unsaved') }}</span>
        <n-button :disabled="!mod" :loading="busy === 'check'" @click="check"><template #icon><n-icon :component="ListCheck" /></template>{{ t('me.check') }}</n-button>
        <n-button type="primary" :disabled="!mod" :loading="busy === 'save'" @click="save()"><template #icon><n-icon :component="DeviceFloppy" /></template>{{ t('me.save') }}</n-button>
      </div>
      <div v-if="mod && mod.readonly" class="hint ro">{{ t('me.readonly') }}</div>
    </div>

    <div v-if="!mod" class="panel empty"><div class="big">{{ t('me.empty') }}</div></div>
    <template v-else>
      <div v-if="result && (result.problems.length || result.warnings.length || result.okShown)" class="panel res">
        <div v-if="!result.problems.length && !result.warnings.length" class="ok">✓ {{ t('me.checkOk') }}</div>
        <template v-if="result.problems.length">
          <div class="rt bad">{{ t('me.problems') }}</div>
          <div v-for="(p, i) in result.problems" :key="'p' + i" class="pr"><span v-if="p.where" class="mono w">{{ p.where }}</span>{{ msg(p) }}</div>
        </template>
        <template v-if="result.warnings.length">
          <div class="rt warn">{{ t('me.warnings') }}</div>
          <div v-for="(p, i) in result.warnings" :key="'w' + i" class="pr"><span v-if="p.where" class="mono w">{{ p.where }}</span>{{ msg(p) }}</div>
        </template>
      </div>

      <n-tabs v-model:value="tab" type="line" animated class="tabs">
        <!-- 基本信息 -->
        <n-tab-pane name="mod" :tab="t('me.tab.mod')">
          <div class="panel">
            <div class="grid g3">
              <div><div class="label">{{ t('me.f.name') }}</div><n-input v-model:value="mod.name" class="mono" /><div class="hint">{{ t('me.f.nameHint') }}</div></div>
              <div><div class="label">{{ t('me.f.title') }}</div><n-input v-model:value="mod.title" /></div>
              <div><div class="label">{{ t('me.f.prefix') }}</div><n-input v-model:value="mod.prefix" class="mono" /><div class="hint">{{ t('me.f.prefixHint') }}</div></div>
            </div>
            <div class="row wrap" style="margin-top:16px">
              <span class="chip">{{ t('me.f.stats', { cards: mod.cards.length, powers: mod.powers.length, relics: mod.relics.length }) }}</span>
              <span v-if="variantNames.length" class="chip">{{ t('me.f.variants', { list: joinList(variantNames) }) }}</span>
            </div>
            <div v-if="pyFiles.length" class="hint">{{ t('me.f.python', { files: joinList(pyFiles) }) }}</div>
            <div v-if="!charIds.length && mod.decks && mod.decks.length" class="hint">{{ t('me.legacyNote') }}</div>
          </div>
        </n-tab-pane>

        <!-- 角色 -->
        <n-tab-pane name="char" :tab="t('me.tab.char')">
          <div v-for="cid in charIds" :key="cid" class="panel">
            <div class="grid g5">
              <div><div class="label">{{ t('me.c.id') }}</div><n-input :value="cid" class="mono" @change="(v) => renameChar(cid, v)" @update:value="() => {}" /></div>
              <div><div class="label">{{ t('me.c.name') }}</div><n-input v-model:value="mod.characters[cid].name" /></div>
              <div><div class="label">{{ t('me.c.hp') }}</div><n-input-number v-model:value="mod.characters[cid].hp" :min="1" :max="999" /></div>
              <div><div class="label">{{ t('me.c.energy') }}</div><n-input-number v-model:value="mod.characters[cid].energy" :min="0" :max="10" /></div>
              <div><div class="label">{{ t('me.c.gold') }}</div><n-input-number v-model:value="mod.characters[cid].gold" :min="0" :max="9999" /></div>
            </div>
            <div class="grid g2" style="margin-top:18px">
              <div>
                <div class="label">{{ t('me.c.deck') }} <span class="faint">{{ t('me.c.deckN', { n: deckCount(cid) }) }}</span></div>
                <div v-for="(it, i) in deckRows(cid)" :key="i" class="deckrow">
                  <n-select size="small" filterable :value="it.id" :options="ctx.cardOptions" @update:value="(v) => setDeck(cid, i, { ...it, id: v })" />
                  <n-input-number size="small" class="cnt" :value="it.n" :min="1" :max="20" @update:value="(v) => setDeck(cid, i, { ...it, n: v || 1 })" />
                  <n-button quaternary size="small" @click="delDeck(cid, i)"><template #icon><n-icon :component="Trash" /></template></n-button>
                </div>
                <n-select size="small" filterable :value="null" :options="ctx.cardOptions" :placeholder="'+ ' + t('me.c.pickCard')" style="margin-top:6px" @update:value="(v) => addDeck(cid, v)" />
              </div>
              <div>
                <div class="label">{{ t('me.c.relics') }}</div>
                <n-select multiple filterable tag :value="mod.characters[cid].relics" :options="relicOptions" @update:value="(v) => (mod.characters[cid].relics = v)" />
                <div class="label" style="margin-top:18px">{{ t('me.c.pool') }}</div>
                <div class="row wrap"><span v-for="r in poolByRarity" :key="r.rarity" class="chip">{{ tr('rarity.', r.rarity) }} · {{ r.n }}</span></div>
              </div>
            </div>
            <div style="margin-top:14px"><n-button size="small" quaternary type="error" @click="delChar(cid)">{{ t('me.c.remove') }}</n-button></div>
          </div>
          <n-button dashed @click="addChar"><template #icon><n-icon :component="Plus" /></template>{{ t('me.c.add') }}</n-button>
        </n-tab-pane>

        <!-- 卡牌 -->
        <n-tab-pane name="cards" :tab="t('me.tab.cards') + ' · ' + mod.cards.length">
          <div class="split">
            <div class="panel listp">
              <div class="row"><n-input v-model:value="q" size="small" clearable :placeholder="t('me.k.search')" /><n-button size="small" type="primary" @click="addCard"><template #icon><n-icon :component="Plus" /></template></n-button></div>
              <div class="items">
                <div v-for="c in filteredCards" :key="c._i" class="item" :class="{ on: sel.card === c._i }" @click="sel.card = c._i">
                  <span class="cost">{{ c.cost === null || c.cost === undefined ? '–' : c.cost }}</span>
                  <div class="in"><div class="nm">{{ c.name || c.id }}</div><div class="sb mono">{{ c.id }} · {{ tr('ctype.', c.type) }} · {{ tr('rarity.', c.rarity) }}</div></div>
                </div>
                <div v-if="!mod.cards.length" class="hint">{{ t('me.k.none') }}</div>
              </div>
            </div>
            <div v-if="card" class="panel edit">
              <div class="row between">
                <h3 style="margin:0">{{ card.name || card.id }}</h3>
                <div class="row"><n-button size="small" @click="dupCard"><template #icon><n-icon :component="Copy" /></template>{{ t('me.k.dup') }}</n-button>
                  <n-button size="small" type="error" secondary @click="delCard"><template #icon><n-icon :component="Trash" /></template>{{ t('me.k.del') }}</n-button></div>
              </div>
              <div class="grid g3" style="margin-top:14px">
                <div><div class="label">{{ t('me.k.id') }}</div><n-input v-model:value="card.id" class="mono" :placeholder="t('me.k.idHint')" /></div>
                <div><div class="label">{{ t('me.k.name') }}</div><n-input v-model:value="card.name" /></div>
                <div><div class="label">{{ t('me.k.upName') }}</div><n-input :value="card.upgrade.name || ''" :placeholder="(card.name || '') + '+'" @update:value="(v) => (card.upgrade.name = v || undefined)" /></div>
                <div><div class="label">{{ t('me.k.type') }}</div><n-select v-model:value="card.type" :options="schema.types.map((v) => ({ value: v, label: tr('ctype.', v) }))" /></div>
                <div><div class="label">{{ t('me.k.rarity') }}</div><n-select v-model:value="card.rarity" :options="schema.rarities.map((v) => ({ value: v, label: tr('rarity.', v) }))" /></div>
                <div><div class="label">{{ t('me.k.target') }}</div><n-select v-model:value="card.target" :options="schema.targets.map((v) => ({ value: v, label: t('me.tgt.' + v) }))" /></div>
                <div><div class="label">{{ t('me.k.cost') }}</div>
                  <div class="row"><n-input-number :value="card.cost" :min="0" :max="9" :disabled="card.cost === null" style="width:110px" @update:value="(v) => (card.cost = v ?? 0)" />
                    <n-checkbox :checked="card.cost === null" @update:checked="(v) => (card.cost = v ? null : 1)">{{ t('me.k.unplayable') }}</n-checkbox></div></div>
                <div><div class="label">{{ t('me.k.upCost') }}</div><n-input-number :value="card.upgrade.cost ?? null" :min="0" :max="9" clearable :placeholder="t('me.k.upSame')" @update:value="(v) => (card.upgrade.cost = v ?? undefined)" /></div>
                <div><div class="label">{{ t('me.k.inPool') }}</div><n-switch :value="card.pool !== false" @update:value="(v) => (card.pool = v)" /></div>
              </div>
              <div style="margin-top:14px"><div class="label">{{ t('me.k.keywords') }}</div>
                <n-checkbox-group :value="card.keywords" @update:value="(v) => (card.keywords = v)"><div class="row wrap">
                  <n-checkbox v-for="k in schema.keywords.filter((k) => k !== 'Unplayable')" :key="k" :value="k" :label="t('me.kw.' + k)" /></div></n-checkbox-group></div>
              <div style="margin-top:16px"><div class="label">{{ t('me.k.vars') }}</div>
                <table class="vars">
                  <thead><tr><th>{{ t('me.k.varName') }}</th><th>{{ t('me.k.base') }}</th><th>{{ t('me.k.up') }}</th><th></th></tr></thead>
                  <tbody>
                    <tr v-for="v in varNames" :key="v">
                      <td class="mono">{{ v }}</td>
                      <td><n-input-number size="small" :value="card.vars[v] ?? null" @update:value="(x) => setVar(v, x, false)" /></td>
                      <td><n-input-number size="small" :value="card.upgrade.vars[v] ?? null" clearable :placeholder="t('me.k.upSame')" @update:value="(x) => setVar(v, x, true)" /></td>
                      <td><n-button quaternary size="tiny" @click="delVar(v)"><template #icon><n-icon :component="Trash" /></template></n-button></td>
                    </tr>
                  </tbody>
                </table>
                <div class="row" style="margin-top:6px"><n-input v-model:value="newVar" size="small" class="mono" style="width:160px" :placeholder="'dmg'" @keyup.enter="addVar" />
                  <n-button size="small" :disabled="!newVar" @click="addVar">{{ t('me.k.addVar') }}</n-button></div>
                <div class="hint">{{ t('me.k.varsHint') }}</div>
              </div>
              <div style="margin-top:16px"><div class="label">{{ t('me.k.text') }}</div>
                <n-input v-model:value="card.text" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :placeholder="t('me.k.textHint')" /></div>
              <div style="margin-top:18px">
                <div class="row between"><div class="label" style="margin:0">{{ t('me.k.effects') }}</div>
                  <n-checkbox :checked="yamlMode" @update:checked="setYamlMode">{{ t('me.k.yaml') }}</n-checkbox></div>
                <div style="margin-top:8px">
                  <template v-if="yamlMode">
                    <n-input v-model:value="yamlText" type="textarea" class="mono" :autosize="{ minRows: 6, maxRows: 30 }" @blur="applyYaml" />
                    <div v-if="yamlErr" class="hint bad">{{ t('me.k.yamlBad', { err: yamlErr }) }}</div>
                  </template>
                  <mod-effects v-else v-model="card.effects" :schema="schema" :ctx="ctx" />
                </div>
              </div>
              <div style="margin-top:16px" class="grid g3"><div><div class="label">{{ t('me.k.ai') }}</div>
                <n-input-number :value="(card.ai || {}).value ?? null" clearable :step="0.5" placeholder="" @update:value="(v) => setAi(v)" /><div class="hint">{{ t('me.k.aiHint') }}</div></div></div>
            </div>
          </div>
        </n-tab-pane>

        <!-- 能力 -->
        <n-tab-pane name="powers" :tab="t('me.tab.powers') + ' · ' + mod.powers.length">
          <div class="split">
            <div class="panel listp">
              <n-button size="small" type="primary" block @click="addPower"><template #icon><n-icon :component="Plus" /></template>{{ t('me.p.add') }}</n-button>
              <div class="items">
                <div v-for="(p, i) in mod.powers" :key="i" class="item" :class="{ on: sel.power === i }" @click="sel.power = i">
                  <div class="in"><div class="nm">{{ p.name || p.id }}</div><div class="sb mono">{{ p.id }} · {{ p.type === 'Debuff' ? t('me.p.debuff') : t('me.p.buff') }}</div></div>
                </div>
                <div v-if="!mod.powers.length" class="hint">{{ t('me.p.none') }}</div>
              </div>
            </div>
            <div v-if="power" class="panel edit">
              <div class="row between"><h3 style="margin:0">{{ power.name || power.id }}</h3>
                <n-button size="small" type="error" secondary @click="mod.powers.splice(sel.power, 1); sel.power = 0"><template #icon><n-icon :component="Trash" /></template>{{ t('me.k.del') }}</n-button></div>
              <div class="grid g3" style="margin-top:14px">
                <div><div class="label">{{ t('me.k.id') }}</div><n-input v-model:value="power.id" class="mono" /></div>
                <div><div class="label">{{ t('me.k.name') }}</div><n-input v-model:value="power.name" /></div>
                <div><div class="label">{{ t('me.p.kind') }}</div><n-select v-model:value="power.type" :options="[{ value: 'Buff', label: t('me.p.buff') }, { value: 'Debuff', label: t('me.p.debuff') }]" /></div>
                <div><div class="label">{{ t('me.p.stack') }}</div><n-select v-model:value="power.stack" :options="[{ value: 'Counter', label: t('me.p.counter') }, { value: 'Single', label: t('me.p.single') }]" /></div>
                <div><div class="label">{{ t('me.p.max') }}</div><n-input-number :value="power.max ?? null" clearable :min="1" @update:value="(v) => (power.max = v ?? undefined)" /></div>
                <div><div class="label">{{ t('me.p.decay') }}</div><n-input-number :value="power.decay ?? null" clearable :min="1" @update:value="(v) => (power.decay = v ?? undefined)" /><div class="hint">{{ t('me.p.decayHint') }}</div></div>
                <div><div class="label">{{ t('me.p.expire') }}</div><n-switch :value="!!power.expire" @update:value="(v) => (power.expire = v ? 'turn_end' : undefined)" /></div>
              </div>
              <div style="margin-top:14px"><div class="label">{{ t('me.k.text') }}</div><n-input v-model:value="power.text" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" /></div>
              <div style="margin-top:16px"><div class="label">{{ t('me.p.triggers') }}</div><mod-triggers v-model="power.triggers" :schema="schema" :ctx="ctx" /></div>
            </div>
          </div>
        </n-tab-pane>

        <!-- 遗物 -->
        <n-tab-pane name="relics" :tab="t('me.tab.relics') + ' · ' + mod.relics.length">
          <div class="split">
            <div class="panel listp">
              <n-button size="small" type="primary" block @click="addRelic"><template #icon><n-icon :component="Plus" /></template>{{ t('me.r.add') }}</n-button>
              <div class="items">
                <div v-for="(r, i) in mod.relics" :key="i" class="item" :class="{ on: sel.relic === i }" @click="sel.relic = i">
                  <div class="in"><div class="nm">{{ r.name || r.id }}</div><div class="sb mono">{{ r.id }} · {{ t('me.rr.' + r.rarity) }}</div></div>
                </div>
                <div v-if="!mod.relics.length" class="hint">{{ t('me.r.none') }}</div>
              </div>
            </div>
            <div v-if="relic" class="panel edit">
              <div class="row between"><h3 style="margin:0">{{ relic.name || relic.id }}</h3>
                <n-button size="small" type="error" secondary @click="mod.relics.splice(sel.relic, 1); sel.relic = 0"><template #icon><n-icon :component="Trash" /></template>{{ t('me.k.del') }}</n-button></div>
              <div class="grid g3" style="margin-top:14px">
                <div><div class="label">{{ t('me.k.id') }}</div><n-input v-model:value="relic.id" class="mono" /></div>
                <div><div class="label">{{ t('me.k.name') }}</div><n-input v-model:value="relic.name" /></div>
                <div><div class="label">{{ t('me.r.rarity') }}</div><n-select v-model:value="relic.rarity" :options="schema.relic_rarities.map((v) => ({ value: v, label: t('me.rr.' + v) }))" /></div>
                <div><div class="label">{{ t('me.r.inPool') }}</div><n-switch :value="relic.pool !== false" @update:value="(v) => (relic.pool = v)" /></div>
              </div>
              <div style="margin-top:14px"><div class="label">{{ t('me.k.text') }}</div><n-input v-model:value="relic.text" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" /></div>
              <div style="margin-top:16px"><div class="label">{{ t('me.p.triggers') }}</div><mod-triggers v-model="relic.triggers" :schema="schema" :ctx="ctx" /></div>
            </div>
          </div>
        </n-tab-pane>

        <!-- 试跑 -->
        <n-tab-pane name="test" :tab="t('me.tab.test')">
          <div v-if="!charIds.length" class="panel empty"><div class="big">{{ t('me.x.needChar') }}</div></div>
          <template v-else>
            <div class="panel">
              <div class="grid g4">
                <div><div class="label">{{ t('me.x.char') }}</div><n-select v-model:value="test.char" :options="charIds.map((c) => ({ value: c, label: mod.characters[c].name + ' (' + c + ')' }))" /></div>
                <div><div class="label">{{ t('me.x.runs') }}</div><n-input-number v-model:value="test.n" :min="1" :max="5000" />
                  <div class="quick"><button v-for="x in [20, 100, 400]" :key="x" :class="{ on: test.n === x }" @click="test.n = x">{{ x }}</button></div></div>
                <div><div class="label">{{ t('me.x.asc') }} <b class="accent">A{{ test.asc }}</b></div><n-slider v-model:value="test.asc" :min="0" :max="10" :step="1" /></div>
                <div><div class="label">{{ t('me.x.agent') }}</div><n-select v-model:value="test.agent" :options="agentOptions" /></div>
              </div>
              <div class="hint">{{ t('me.x.saveFirst') }}</div>
            </div>
            <div class="grid g2" style="margin-top:16px">
              <div class="panel">
                <h3>{{ t('me.x.batch') }}</h3>
                <div class="hint" style="margin:-6px 0 14px">{{ t('me.x.batchHint') }}</div>
                <n-button type="primary" :loading="busy === 'batch'" @click="runBatch"><template #icon><n-icon :component="PlayerPlay" /></template>{{ t('me.x.batchBtn') }}</n-button>
              </div>
              <div class="panel">
                <h3>{{ t('me.x.ab') }}</h3>
                <div class="hint" style="margin:-6px 0 14px">{{ t('me.x.abHint') }}</div>
                <div class="row wrap">
                  <n-select v-model:value="test.card" filterable :options="ctx.cardOptions" :placeholder="t('me.x.card')" style="width:260px" />
                  <n-checkbox v-model:checked="test.up">{{ t('me.x.upgraded') }}</n-checkbox>
                  <n-button type="primary" :disabled="!test.card" :loading="busy === 'ab'" @click="runAB"><template #icon><n-icon :component="Scale" /></template>{{ t('me.x.abBtn') }}</n-button>
                </div>
              </div>
            </div>
            <div class="panel" style="margin-top:16px">
              <h3>{{ t('me.x.recent') }}</h3>
              <div v-if="!myTests.length" class="hint">{{ t('me.x.none') }}</div>
              <div v-for="x in myTests" :key="x.key" class="trow">
                <n-tag size="small" :bordered="false" :type="statusType(x)">{{ t('status.' + statusOf(x)) }}</n-tag>
                <span class="tt">{{ x.title }}</span>
                <span class="faint">{{ fmt.time(x.created) }}</span>
                <div class="sp"></div>
                <template v-if="x.pair"><n-button size="small" :disabled="statusOf(x) !== 'done'" @click="$router.push({ path: '/ab', query: { a: x.a.id, b: x.b.id } })">{{ t('me.x.compare') }}</n-button></template>
                <template v-else><n-button size="small" @click="$router.push(statusOf(x) === 'done' ? '/report/' + x.a.id : '/run/' + x.a.id)">{{ statusOf(x) === 'done' ? t('me.x.report') : t('nav.run') }}</n-button></template>
              </div>
            </div>
          </template>
        </n-tab-pane>
      </n-tabs>
      <div v-if="mod && !mod.readonly && savedName" style="margin-top:22px"><n-button size="small" quaternary type="error" @click="delMod">{{ t('me.delete') }}</n-button></div>
    </template>
  </div>
</template>

<script>
// 编辑中的内容放在模块里（不放在组件里）：切换界面语言 / 切到别的页面再回来时页面会重建，内容不能丢
import { reactive as _reactive, ref as _ref } from 'vue'
const mod = _ref(null)
const openId = _ref(null)
const savedName = _ref(null)
const dirty = _ref(false)
const result = _ref(null)
const cardIds = _ref({})
const tab = _ref('cards')
const sel = _reactive({ card: 0, power: 0, relic: 0 })
const test = _reactive({ char: null, n: 100, asc: 0, agent: 'modai', card: null, up: false })
</script>

<script setup>
import { computed, h, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NCheckbox, NCheckboxGroup, NIcon, NInput, NInputNumber, NSelect, NSlider, NSwitch, NTabs, NTabPane, NTag, useDialog, useMessage } from 'naive-ui'
import { FilePlus, FileImport, FileExport, DeviceFloppy, ListCheck, Plus, Trash, Copy, PlayerPlay, Scale } from '@vicons/tabler'
import yaml from 'js-yaml'
import ModEffects from '../components/ModEffects.vue'
import ModTriggers from '../components/ModTriggers.vue'
import { api, store, fmt } from '../api'
import { t, tr, lang, joinList } from '../i18n'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const schema = ref(null)
const mods = ref([])
const busy = ref('')
const q = ref('')
const newVar = ref('')
let loading = false

// 只改地址栏不通知路由：App.vue 用 fullPath 做页面 key，走 router.replace 会把整页重建、丢掉正在编辑的状态
function setQuery(name) {
  try { window.history.replaceState(window.history.state, '', '#/mods' + (name ? '?mod=' + encodeURIComponent(name) : '')) } catch (e) { /* ignore */ }
}
const msg = (p) => (lang.value === 'zhs' ? p.zhs : p.en)
const modOptions = computed(() => mods.value.map((m) => ({ value: m.id, label: m.title, m })))
function modLabel(o) {
  const m = o.m
  return h('span', {}, [o.label, ' ', h('span', { class: 'faint mono', style: 'font-size:11.5px' }, m.id),
    h('span', { class: 'tagm' + (m.user ? ' mine' : '') }, m.user ? t('me.mine') : t('me.builtin')),
    m.fullrun ? null : h('span', { class: 'tagm' }, t('me.legacy'))])
}
const charIds = computed(() => Object.keys((mod.value && mod.value.characters) || {}))
const variantNames = computed(() => Object.keys((mod.value && mod.value.variants) || {}))
const pyFiles = computed(() => Object.keys((mod.value && mod.value.files) || {}).filter((f) => f.endsWith('.py')))
const ctx = computed(() => ({
  powerOptions: ((mod.value && mod.value.powers) || []).map((p) => ({ value: p.id, label: (p.name || p.id) + ' · ' + p.id })),
  cardOptions: ((mod.value && mod.value.cards) || []).map((c) => ({ value: c.id, label: (c.name || c.id) + ' · ' + c.id })),
}))
const relicOptions = computed(() => mod.value.relics.map((r) => ({ value: r.id, label: (r.name || r.id) + ' · ' + r.id })))
const agentOptions = computed(() => ((store.catalog && store.catalog.agents_batch) || []).filter((a) => a.available !== false).map((a) => ({ value: a.id, label: a.name })))
const poolByRarity = computed(() => {
  const out = {}
  for (const c of mod.value.cards) if (c.pool !== false) out[c.rarity] = (out[c.rarity] || 0) + 1
  return ['Basic', 'Common', 'Uncommon', 'Rare', 'Token'].filter((r) => out[r]).map((r) => ({ rarity: r, n: out[r] }))
})
const filteredCards = computed(() => {
  const s = q.value.trim().toLowerCase()
  return mod.value.cards.map((c, i) => ({ ...c, _i: i })).filter((c) => !s || (c.id + ' ' + (c.name || '')).toLowerCase().includes(s))
})
const card = computed(() => mod.value && mod.value.cards[sel.card])
const power = computed(() => mod.value && mod.value.powers[sel.power])
const relic = computed(() => mod.value && mod.value.relics[sel.relic])
const varNames = computed(() => (card.value ? [...new Set([...Object.keys(card.value.vars || {}), ...Object.keys(card.value.upgrade.vars || {})])] : []))

// ---------------------------------------------------------------- 打开 / 新建 / 导入
function fixup(m) {
  m.cards = m.cards || []
  m.powers = m.powers || []
  m.relics = m.relics || []
  m.characters = m.characters || {}
  for (const c of m.cards) {
    c.upgrade = c.upgrade || {}
    c.upgrade.vars = c.upgrade.vars || {}
    c.vars = c.vars || {}
    c.keywords = c.keywords || []
    c.effects = c.effects || []
  }
  for (const p of [...m.powers, ...m.relics]) p.triggers = p.triggers || []
  return m
}
function setMod(m, saved) {
  loading = true
  delete m._check
  mod.value = fixup(m)
  savedName.value = saved
  sel.card = 0; sel.power = 0; sel.relic = 0
  test.char = charIds.value[0] || null
  test.card = null
  cardIds.value = {}
  nextTick(() => { dirty.value = false; loading = false })
}
watch(mod, () => { if (!loading) dirty.value = true }, { deep: true })
function confirmDiscard() {
  if (!mod.value || !dirty.value) return Promise.resolve(true)
  return new Promise((res) => dialog.warning({ title: t('me.unsaved'), content: t('me.discardQ'), positiveText: t('common.ok'), negativeText: t('common.cancel'),
    onPositiveClick: () => res(true), onNegativeClick: () => res(false), onClose: () => res(false) }))
}
async function openMod(id) {
  if (!(await confirmDiscard())) return
  try {
    const m = await api.get('/api/modeditor/mod/' + id)
    openId.value = id
    result.value = null
    setMod(m, id)
    tab.value = String(route.query.tab || (charIds.value.length ? 'cards' : 'mod'))
    const ci = m.cards.findIndex((c) => c.id === route.query.card)
    if (ci >= 0) sel.card = ci
    setQuery(id)
  } catch (e) { message.error(e.message) }
}
async function newMod() {
  if (!(await confirmDiscard())) return
  const m = await api.get('/api/modeditor/new')
  let name = 'my_mod'
  for (let i = 2; mods.value.some((x) => x.id === name); i++) name = 'my_mod' + i
  m.name = name
  openId.value = null
  result.value = null
  setMod(m, null)
  dirty.value = true
  tab.value = 'char'
}
async function importZip(ev) {
  const f = ev.target.files[0]
  ev.target.value = ''
  if (!f || !(await confirmDiscard())) return
  const form = new FormData()
  form.append('file', f)
  try {
    const m = await api.upload('/api/modeditor/import', form)
    const chk = m._check
    openId.value = null
    setMod(m, null)
    nextTick(() => { dirty.value = true })
    result.value = chk && (chk.problems.length || chk.warnings.length) ? chk : null
    message.success(t('me.imported', { name: m.name }))
  } catch (e) { message.error(e.message, { duration: 8000 }) }
}
async function loadMods() { mods.value = await api.get('/api/modeditor/mods') }

// ---------------------------------------------------------------- 保存 / 检查
function payload() { return { mod: JSON.parse(JSON.stringify(mod.value)), old_name: savedName.value } }
async function check() {
  busy.value = 'check'
  try {
    result.value = { ...(await api.post('/api/modeditor/validate', payload())), okShown: true }
  } catch (e) { message.error(e.message) } finally { busy.value = '' }
}
async function save(quiet) {
  busy.value = busy.value || 'save'
  try {
    const r = await api.post('/api/modeditor/save', payload())
    result.value = { ...r, okShown: !quiet }
    cardIds.value = r.cards || {}
    savedName.value = r.name
    openId.value = r.name
    mod.value.readonly = false
    await nextTick()
    dirty.value = false
    await loadMods()
    setQuery(r.name)
    if (!quiet) message.success(t('me.saved', { path: r.name }))
    return r
  } catch (e) {
    message.error(e.message, { duration: 8000 })
    return null
  } finally { if (busy.value === 'save') busy.value = '' }
}
async function delMod() {
  dialog.warning({ title: t('me.delete'), content: t('me.delQ', { name: savedName.value }), positiveText: t('common.delete'), negativeText: t('common.cancel'),
    onPositiveClick: async () => {
      await api.del('/api/modeditor/mod/' + savedName.value)
      mod.value = null; savedName.value = null; openId.value = null
      setQuery(null)
      loadMods()
    } })
}

// ---------------------------------------------------------------- 角色
function deckRows(cid) {
  return (mod.value.characters[cid].starting_deck || []).map((s) => {
    const m = String(s).match(/^(.*?)(?:\s*[×*]\s*(\d+)|\s+x(\d+))?$/)
    return { id: m[1], n: Number(m[2] || m[3] || 1) }
  })
}
const deckStr = (it) => (it.n > 1 ? `${it.id}×${it.n}` : it.id)
const deckCount = (cid) => deckRows(cid).reduce((s, x) => s + x.n, 0)
function setDeck(cid, i, it) { const r = deckRows(cid); r[i] = it; mod.value.characters[cid].starting_deck = r.map(deckStr) }
function delDeck(cid, i) { const r = deckRows(cid); r.splice(i, 1); mod.value.characters[cid].starting_deck = r.map(deckStr) }
function addDeck(cid, id) { if (id) mod.value.characters[cid].starting_deck = [...(mod.value.characters[cid].starting_deck || []), id] }
function renameChar(old, v) {
  v = String(v || '').trim()
  if (!v || v === old || mod.value.characters[v]) return
  const out = {}
  for (const [k, x] of Object.entries(mod.value.characters)) out[k === old ? v : k] = k === old ? { ...x, id: v } : x
  mod.value.characters = out
  if (test.char === old) test.char = v
}
function addChar() {
  let id = 'Hero'
  for (let i = 2; mod.value.characters[id]; i++) id = 'Hero' + i
  mod.value.characters = { ...mod.value.characters, [id]: { id, name: id, hp: 75, energy: 3, gold: 99, starting_deck: [], relics: [] } }
  if (!test.char) test.char = id
}
function delChar(cid) { const c = { ...mod.value.characters }; delete c[cid]; mod.value.characters = c }

// ---------------------------------------------------------------- 卡牌
function uniq(base, list) { let id = base; for (let i = 2; list.some((x) => x.id === id); i++) id = base + '_' + i; return id }
function addCard() {
  const id = uniq('NEW_CARD', mod.value.cards)
  mod.value.cards.push({ id, name: id, type: 'Attack', rarity: 'Common', cost: 1, target: 'AnyEnemy', keywords: [], vars: { dmg: 8 },
    upgrade: { vars: { dmg: 11 } }, effects: [{ op: 'damage', amount: 'dmg' }], text: '', pool: true })
  sel.card = mod.value.cards.length - 1
  q.value = ''
}
function dupCard() {
  const c = JSON.parse(JSON.stringify(card.value))
  c.id = uniq(c.id, mod.value.cards)
  delete c.class
  mod.value.cards.splice(sel.card + 1, 0, c)
  sel.card += 1
}
function delCard() { mod.value.cards.splice(sel.card, 1); sel.card = Math.max(0, sel.card - 1) }
function setVar(v, x, up) {
  const o = up ? card.value.upgrade.vars : card.value.vars
  if (x === null || x === undefined) delete o[v]
  else o[v] = x
}
function delVar(v) { delete card.value.vars[v]; delete card.value.upgrade.vars[v] }
function addVar() {
  const v = newVar.value.trim()
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(v)) return
  card.value.vars[v] = card.value.vars[v] ?? 0
  newVar.value = ''
}
function setAi(v) {
  if (v === null || v === undefined) { if (card.value.ai) delete card.value.ai.value; return }
  card.value.ai = { ...(card.value.ai || {}), value: v }
}
const yamlMode = ref(false)
const yamlText = ref('')
const yamlErr = ref('')
function setYamlMode(on) {
  if (on) { yamlText.value = yaml.dump(card.value.effects || [], { lineWidth: 120 }); yamlErr.value = '' } else if (!applyYaml()) return
  yamlMode.value = on
}
function applyYaml() {
  try {
    const v = yaml.load(yamlText.value) || []
    if (!Array.isArray(v)) throw new Error('list')
    card.value.effects = v
    yamlErr.value = ''
    return true
  } catch (e) { yamlErr.value = e.message.split('\n')[0]; return false }
}
watch(() => sel.card, () => { if (yamlMode.value) yamlText.value = yaml.dump((card.value && card.value.effects) || [], { lineWidth: 120 }) })

// ---------------------------------------------------------------- 能力 / 遗物
function addPower() {
  const id = uniq('NEW_POWER', mod.value.powers)
  mod.value.powers.push({ id, name: id, type: 'Buff', stack: 'Counter', triggers: [], vars: {}, text: '' })
  sel.power = mod.value.powers.length - 1
}
function addRelic() {
  const id = uniq('NEW_RELIC', mod.value.relics)
  mod.value.relics.push({ id, name: id, rarity: 'Common', triggers: [], vars: {}, text: '', pool: true })
  sel.relic = mod.value.relics.length - 1
}

// ---------------------------------------------------------------- 试跑
async function ready() {
  // 自带的只读 mod 没改过：直接用；否则先保存
  let name = savedName.value
  if (!name || dirty.value || (mod.value.readonly && dirty.value)) {
    const r = await save(true)
    if (!r) return null
    name = r.name
  } else if (!Object.keys(cardIds.value).length) {
    const r = await api.get('/api/modeditor/check/' + name)
    result.value = r.problems.length ? r : null
    if (!r.ok) { message.error(t('me.x.fixFirst')); return null }
    cardIds.value = r.cards || {}
  }
  if (result.value && result.value.problems && result.value.problems.length) { message.error(t('me.x.fixFirst')); return null }
  return name
}
const baseParams = (name) => ({ mod: name, char: test.char, asc: test.asc, n: test.n, start: 0, agent: test.agent, procs: (store.catalog && store.catalog.cpu) || 1, variants: [], force: [], replace: [] })
async function runBatch() {
  busy.value = 'batch'
  try {
    const name = await ready()
    if (!name) return
    const m = await api.post('/api/runs', { kind: 'batch', params: baseParams(name), title: t('me.x.titleBatch', { mod: mod.value.title || name, asc: test.asc, n: test.n }), lang: lang.value })
    message.success(t('me.x.started'))
    store.loadRuns()
    router.push('/run/' + m.id)
  } catch (e) { message.error(e.message, { duration: 8000 }) } finally { busy.value = '' }
}
async function runAB() {
  busy.value = 'ab'
  try {
    const name = await ready()
    if (!name) return
    const gid = cardIds.value[test.card]
    if (!gid) { message.error(t('me.x.fixFirst')); return }
    const cn = (mod.value.cards.find((c) => c.id === test.card) || {}).name || test.card
    const tag = { mod: mod.value.title || name, asc: test.asc, n: test.n, card: cn + (test.up ? '+' : '') }
    const A = await api.post('/api/runs', { kind: 'batch', params: { ...baseParams(name), ab_group: 'A' }, title: t('me.x.titleA', tag), lang: lang.value })
    const B = await api.post('/api/runs', { kind: 'batch', params: { ...baseParams(name), force: [gid + (test.up ? '+' : '')], ab_group: 'B', ab_pair: A.id }, title: t('me.x.titleB', tag), lang: lang.value })
    message.success(t('me.x.started'))
    await store.loadRuns()
    void B
  } catch (e) { message.error(e.message, { duration: 8000 }) } finally { busy.value = '' }
}
const myTests = computed(() => {
  if (!savedName.value) return []
  const runs = store.runs.filter((r) => r.kind === 'batch' && r.params && r.params.mod === savedName.value)
  const byId = Object.fromEntries(runs.map((r) => [r.id, r]))
  const out = []
  for (const r of runs) {
    if (r.params.ab_group === 'A') continue
    if (r.params.ab_group === 'B' && byId[r.params.ab_pair]) out.push({ key: r.id, pair: true, a: byId[r.params.ab_pair], b: r, title: r.title, created: r.created })
    else out.push({ key: r.id, pair: false, a: r, title: r.title, created: r.created })
  }
  return out.sort((x, y) => String(y.created).localeCompare(String(x.created))).slice(0, 12)
})
function statusOf(x) {
  const s = [x.a.status, x.b ? x.b.status : 'done']
  if (s.includes('failed')) return 'failed'
  if (s.includes('cancelled')) return 'cancelled'
  if (s.includes('running')) return 'running'
  return s.every((v) => v === 'done') ? 'done' : s[0]
}
const statusType = (x) => ({ done: 'success', failed: 'error', running: 'warning' })[statusOf(x)] || 'default'

onMounted(async () => {
  schema.value = await api.get('/api/modeditor/schema')
  await loadMods()
  if (route.query.mod && String(route.query.mod) !== openId.value) openMod(String(route.query.mod))
  else if (mod.value) setQuery(savedName.value)
})
</script>

<style scoped>
.bar .wrap { flex-wrap: wrap; }
.opener { width: 340px; }
.sp { flex: 1; }
.ro { color: #E0B26C; }
.res { border-color: #3A3A41; }
.res .ok { color: #8FBF8F; font-weight: 600; }
.rt { font-size: 13px; font-weight: 650; margin: 4px 0 6px; }
.rt.bad { color: #E06C6C; }
.rt.warn { color: #E0B26C; margin-top: 10px; }
.pr { font-size: 12.5px; color: #CFCAC2; line-height: 1.6; padding: 2px 0; }
.pr .w { color: #8A857E; margin-right: 8px; font-size: 11.5px; }
.bad { color: #E06C6C; }
.tabs { margin-top: 16px; }
.g5 { grid-template-columns: 1.1fr 1.3fr .8fr .8fr .8fr; }
.deckrow { display: grid; grid-template-columns: 1fr 90px 34px; gap: 6px; margin-bottom: 6px; }
.split { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 16px; align-items: start; }
.split .panel + .panel { margin-top: 0; }
.listp { padding: 14px; position: sticky; top: 12px; }
.items { margin-top: 10px; max-height: 68vh; overflow: auto; display: flex; flex-direction: column; gap: 2px; }
.item { display: flex; gap: 10px; align-items: center; padding: 7px 8px; border-radius: 8px; cursor: pointer; }
.item:hover { background: #24242A; }
.item.on { background: rgba(217,119,87,.14); }
.cost { width: 22px; height: 22px; border-radius: 50%; background: #2C2C33; color: #F0A486; font-size: 12px; font-weight: 700; display: grid; place-items: center; flex: none; }
.in { min-width: 0; }
.nm { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sb { font-size: 10.5px; color: #77736C; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vars { border-collapse: collapse; }
.vars th { font-size: 11.5px; color: #9C978F; font-weight: 500; text-align: left; padding: 2px 8px 4px 0; }
.vars td { padding: 2px 8px 2px 0; }
.vars td:first-child { min-width: 90px; font-size: 12.5px; color: #CFCAC2; }
.quick { display: flex; gap: 6px; margin-top: 6px; }
.quick button { background: #26262B; border: 1px solid #303036; color: #B9B4AC; border-radius: 6px; padding: 2px 8px; font-size: 12px; cursor: pointer; }
.quick button.on { border-color: #D97757; color: #F0A486; }
.accent { color: #F0A486; }
.trow { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid #26262B; font-size: 13px; }
.tt { font-weight: 500; }
:deep(.tagm) { margin-left: 8px; font-size: 10.5px; padding: 1px 6px; border-radius: 6px; background: #2A2A30; color: #9C978F; }
:deep(.tagm.mine) { background: rgba(217,119,87,.16); color: #F0A486; }
</style>
