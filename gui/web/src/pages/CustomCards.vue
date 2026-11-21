<template>
  <div class="page" data-page="cards">
    <div class="panel bar">
      <div class="row wrap">
        <n-select class="opener" :value="openId" :options="libOptions" :placeholder="t('cc.openPh')" data-testid="card-open" @update:value="openLib" />
        <n-button data-testid="card-new" @click="fresh">{{ t('cc.new') }}</n-button>
        <n-button data-testid="card-import" @click="$refs.file.click()">{{ t('cc.import') }}</n-button>
        <input ref="file" type="file" accept=".zip,.yaml,.yml" class="hid" @change="onImport" />
        <div class="sp"></div>
        <span v-if="dirty" class="chip">{{ t('cc.unsaved') }}</span>
        <n-button :disabled="!lib" data-testid="card-check" @click="check">{{ t('cc.check') }}</n-button>
        <n-button type="primary" :disabled="!lib" :loading="busy === 'save'" data-testid="card-save" @click="save()">{{ t('cc.save') }}</n-button>
      </div>
      <p class="hint">{{ t('cc.hint') }}</p>
    </div>

    <div v-if="!lib" class="panel empty"><div class="big">{{ t('cc.empty') }}</div></div>
    <template v-else>
      <div v-if="result && ((result.problems || []).length || (result.warnings || []).length)" class="panel" role="alert" data-testid="card-problems">
        <div v-if="(result.problems || []).length" class="bad">{{ t('cc.problems') }}</div>
        <p v-for="(p, i) in result.problems || []" :key="'p' + i" class="pr"><span v-if="p.where" class="mono">{{ p.where }}</span> {{ msg(p) }}</p>
        <div v-if="(result.warnings || []).length" class="warn">{{ t('cc.warnings') }}</div>
        <p v-for="(p, i) in result.warnings || []" :key="'w' + i" class="pr"><span v-if="p.where" class="mono">{{ p.where }}</span> {{ msg(p) }}</p>
      </div>
      <div v-else-if="result && result.ok" class="panel" role="status" data-testid="card-ok">{{ t('cc.checkOk') }}</div>

      <div class="split">
        <div class="panel">
          <div class="row">
            <n-button size="small" type="primary" data-testid="card-add" @click="addCard">{{ t('cc.add') }}</n-button>
          </div>
          <button v-for="(c, i) in lib.cards" :key="i" type="button" class="item" :class="{ on: sel === i }" :data-card-row="c.id" @click="sel = i">
            <span class="nm">{{ c.name || c.id }}</span>
            <span class="sb mono">{{ c.id }}</span>
          </button>
          <p v-if="!lib.cards.length" class="hint">{{ t('cc.none') }}</p>
        </div>

        <div v-if="card" class="panel">
          <div class="row between">
            <h3>{{ card.name || card.id }}</h3>
            <n-button size="small" type="error" secondary data-testid="card-del" @click="delCard">{{ t('cc.del') }}</n-button>
          </div>
          <div class="grid g3">
            <label>{{ t('cc.id') }}<n-input v-model:value="card.id" class="mono" data-testid="card-id" /></label>
            <label>{{ t('cc.cardName') }}<n-input v-model:value="card.name" data-testid="card-name" /></label>
            <label>{{ t('cc.type') }}<n-select v-model:value="card.type" :options="opt(schema.types, 'ctype.')" /></label>
            <label>{{ t('cc.rarity') }}<n-select v-model:value="card.rarity" :options="opt(schema.rarities, 'rarity.')" /></label>
            <label>{{ t('cc.target') }}<n-select v-model:value="card.target" :options="schema.targets.map((v) => ({ value: v, label: t('me.tgt.' + v) }))" /></label>
            <label>{{ t('cc.cost') }}<n-input-number v-model:value="card.cost" :min="0" :max="9" data-testid="card-cost" /></label>
          </div>
          <div class="label">{{ t('cc.keywords') }}</div>
          <n-checkbox-group v-model:value="card.keywords">
            <div class="row wrap">
              <n-checkbox v-for="k in schema.keywords" :key="k" :value="k" :label="t('me.kw.' + k)" />
            </div>
          </n-checkbox-group>
          <div class="label">{{ t('cc.vars') }}</div>
          <div v-for="v in varNames" :key="v" class="row">
            <span class="mono">{{ v }}</span>
            <n-input-number size="small" :value="card.vars[v]" :data-testid="'var-' + v" @update:value="(x) => setVar(v, x, false)" />
            <n-input-number size="small" :value="card.upgrade.vars[v] ?? null" clearable @update:value="(x) => setVar(v, x, true)" />
            <n-button size="tiny" quaternary @click="delVar(v)">{{ t('cc.del') }}</n-button>
          </div>
          <div class="row">
            <n-input v-model:value="newVar" size="small" class="mono" data-testid="new-var" />
            <n-button size="small" data-testid="add-var" @click="addVar">{{ t('cc.addVar') }}</n-button>
          </div>
          <p class="hint">{{ t('cc.varsHint') }}</p>
          <div class="label">{{ t('cc.effects') }}</div>
          <mod-effects v-if="schema.ops" v-model="card.effects" :schema="schema" :ctx="ctx" />
          <label class="bonus">{{ t('cc.bonus') }}
            <n-input-number :value="card.ai.bonus ?? null" clearable data-testid="card-bonus" @update:value="setBonus" />
          </label>
          <p class="hint">{{ t('cc.bonusHint') }}</p>
          <label>{{ t('cc.text') }}<n-input v-model:value="card.text" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" /></label>
        </div>
      </div>

      <div class="panel">
        <h3>{{ t('cc.hero') }}</h3>
        <div class="grid g4">
          <label>{{ t('cc.libName') }}<n-input v-model:value="lib.name" class="mono" data-testid="lib-name" /></label>
          <label>{{ t('cc.libTitle') }}<n-input v-model:value="lib.title" data-testid="lib-title" /></label>
          <label>{{ t('cc.heroName') }}<n-input v-model:value="lib.character.name" /></label>
          <label>{{ t('cc.hp') }}<n-input-number v-model:value="lib.character.hp" :min="1" :max="999" data-testid="hero-hp" /></label>
          <label>{{ t('cc.energy') }}<n-input-number v-model:value="lib.character.energy" :min="1" :max="10" data-testid="hero-energy" /></label>
        </div>
      </div>

      <div class="panel">
        <h3>{{ t('cc.deck') }}</h3>
        <p class="hint">{{ t('cc.deckHint') }}</p>
        <div v-for="(row, i) in lib.deck" :key="i" class="row">
          <n-select :value="row.id" :options="cardOptions" data-testid="deck-card" @update:value="(v) => (row.id = v)" />
          <n-input-number v-model:value="row.count" :min="1" :max="15" />
          <n-checkbox v-model:checked="row.upgrade">{{ t('cc.upgrade') }}</n-checkbox>
          <n-button size="small" quaternary @click="lib.deck.splice(i, 1)">{{ t('cc.del') }}</n-button>
        </div>
        <n-button size="small" data-testid="deck-add" @click="addDeck">{{ t('cc.deckAdd') }}</n-button>
        <div class="grid g4 test">
          <label>{{ t('cc.encounter') }}
            <n-select v-model:value="lib.encounter" :options="encOptions" data-testid="encounter" />
          </label>
          <label>{{ t('cc.turns') }}<n-input-number v-model:value="lib.max_turns" :min="1" :max="30" data-testid="max-turns" /></label>
          <label>{{ t('cc.seed') }}<n-input-number v-model:value="lib.seed" :min="0" :max="2147483647" data-testid="seed" /></label>
          <label>{{ t('cc.fights') }}<n-input-number v-model:value="lib.fights" :min="1" :max="8" data-testid="fights" /></label>
        </div>
        <p class="hint">{{ lib.encounter === 'SYN_BRUTE' ? t('cc.bruteHint') : t('cc.dummyHint') }}</p>
        <n-button type="primary" :loading="busy === 'test'" data-testid="card-test" @click="runTest">{{ t('cc.test') }}</n-button>
        <p v-if="runId" class="hint" data-testid="card-ran">
          <router-link :to="'/run/' + runId">{{ t('cc.openRun') }}</router-link>
          <router-link :to="'/replay/' + runId">{{ t('cc.openReplay') }}</router-link>
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NCheckbox, NCheckboxGroup, NInput, NInputNumber, NSelect, useMessage } from 'naive-ui'
import ModEffects from '../components/ModEffects.vue'
import { api } from '../api'
import { t, tr, lang } from '../i18n'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const schema = ref({ ops: {}, templates: {}, types: [], rarities: [], targets: [], keywords: [], powers: [], once: [], target_specs: [] })
const libs = ref([])
const lib = ref(null)
const saved = ref('')
const sel = ref(0)
const result = ref(null)
const busy = ref('')
const newVar = ref('')
const runId = ref('')
const openId = ref(null)

const card = computed(() => (lib.value && lib.value.cards[sel.value]) || null)
const varNames = computed(() => (card.value ? Object.keys(card.value.vars || {}) : []))
const cardOptions = computed(() => (lib.value ? lib.value.cards.map((c) => ({ value: c.id, label: (c.name || c.id) + ' · ' + c.id })) : []))
const libOptions = computed(() => libs.value.map((row) => ({ value: row.name, label: row.name })))
const encOptions = computed(() => [
  { value: 'DUMMY', label: t('cc.enc.DUMMY') },
  { value: 'SYN_BRUTE', label: t('cc.enc.SYN_BRUTE') },
])
const ctx = computed(() => ({
  powerOptions: (schema.value.powers || []).map((id) => ({ value: id, label: id })),
  cardOptions: cardOptions.value,
}))
const dirty = computed(() => lib.value && JSON.stringify(lib.value) !== saved.value)
const msg = (p) => (lang.value === 'zhs' ? p.zhs : p.en)
const opt = (list, prefix) => (list || []).map((v) => ({ value: v, label: tr(prefix, v) }))

function markSaved() {
  saved.value = JSON.stringify(lib.value)
}
async function loadLists() {
  libs.value = await api.get('/api/custom-cards/libraries')
}
async function fresh() {
  lib.value = await api.get('/api/custom-cards/new')
  sel.value = 0
  result.value = null
  runId.value = ''
  openId.value = null
  markSaved()
  saved.value = ''
}
async function openLib(name) {
  if (!name) return
  const loaded = await api.get('/api/custom-cards/library/' + encodeURIComponent(name))
  lib.value = loaded
  sel.value = 0
  result.value = null
  openId.value = name
  markSaved()
  router.replace({ path: '/cards', query: { lib: name } })
}
function addCard() {
  const id = 'CARD_' + (lib.value.cards.length + 1)
  lib.value.cards.push({
    id, name: id, type: 'Skill', rarity: 'Common', cost: 1, target: 'Self', keywords: [],
    vars: { blk: 5 }, upgrade: { vars: { blk: 8 }, cost: null, name: '' },
    effects: [{ op: 'block', amount: 'blk' }], text: '', pool: true, ai: {},
  })
  sel.value = lib.value.cards.length - 1
}
function delCard() {
  lib.value.cards.splice(sel.value, 1)
  sel.value = Math.max(0, sel.value - 1)
}
function setVar(name, value, up) {
  const box = up ? card.value.upgrade.vars : card.value.vars
  if (value === null || value === undefined) delete box[name]
  else box[name] = value
}
function delVar(name) {
  delete card.value.vars[name]
  delete card.value.upgrade.vars[name]
}
function addVar() {
  const name = newVar.value.trim()
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    message.error(t('cc.varBad'))
    return
  }
  card.value.vars[name] = card.value.vars[name] ?? 0
  newVar.value = ''
}
function setBonus(value) {
  if (!card.value.ai) card.value.ai = {}
  if (value === null || value === undefined) delete card.value.ai.bonus
  else card.value.ai.bonus = value
}
function addDeck() {
  const id = card.value ? card.value.id : (lib.value.cards[0] && lib.value.cards[0].id)
  if (!id) return
  lib.value.deck.push({ id, count: 1, upgrade: false })
}
function payload() {
  return { library: JSON.parse(JSON.stringify(lib.value)), focus: card.value && card.value.id }
}
async function check() {
  busy.value = 'check'
  try {
    result.value = await api.post('/api/custom-cards/validate', payload())
  } catch (e) {
    message.error(e.message)
  } finally {
    busy.value = ''
  }
}
async function save() {
  busy.value = 'save'
  try {
    const res = await api.post('/api/custom-cards/save', payload())
    result.value = res
    if (!res.ok) {
      message.error(t('cc.fix'))
      return null
    }
    lib.value = res.library
    openId.value = res.name
    markSaved()
    await loadLists()
    router.replace({ path: '/cards', query: { lib: res.name } })
    message.success(t('cc.saved'))
    return res
  } catch (e) {
    message.error(e.message)
    return null
  } finally {
    busy.value = ''
  }
}
async function runTest() {
  busy.value = 'test'
  try {
    const res = await api.post('/api/custom-cards/test', payload())
    result.value = res
    if (!res.ok) {
      message.error(t('cc.fix'))
      return
    }
    if (res.library) {
      lib.value = res.library
      markSaved()
    }
    runId.value = res.run_id
    await loadLists()
    message.success(t('cc.tested'))
    router.push('/run/' + res.run_id)
  } catch (e) {
    message.error(e.message)
  } finally {
    busy.value = ''
  }
}
async function onImport(ev) {
  const file = ev.target.files && ev.target.files[0]
  ev.target.value = ''
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await api.upload('/api/custom-cards/import', form)
    if (!res.ok) {
      result.value = res
      message.error(t('cc.fix'))
      return
    }
    lib.value = res.library
    sel.value = 0
    result.value = res
    saved.value = ''
    message.success(t('cc.imported'))
  } catch (e) {
    message.error(e.message)
  }
}
onMounted(async () => {
  schema.value = await api.get('/api/custom-cards/schema')
  await loadLists()
  const query = route.query.lib
  if (query) await openLib(String(query))
  else await fresh()
})
</script>

<style scoped>
.bar .wrap { flex-wrap: wrap; }
.opener { width: 240px; }
.sp { flex: 1; }
.hid { display: none; }
.split { display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 16px; margin-top: 16px; }
.item { display: flex; flex-direction: column; align-items: flex-start; width: 100%; text-align: left; background: transparent; border: 0; color: inherit; padding: 8px; border-radius: 8px; cursor: pointer; }
.item.on, .item:hover { background: #24242A; }
.nm { font-size: 13px; }
.sb { font-size: 11px; color: #77736C; }
.bad { color: #E06C6C; font-weight: 650; }
.warn { color: #E0B26C; font-weight: 650; margin-top: 8px; }
.pr { margin: 4px 0; font-size: 13px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #B9B4AC; }
.g4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.bonus { margin-top: 12px; max-width: 220px; }
.test { margin-top: 16px; }
</style>
