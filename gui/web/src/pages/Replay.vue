<template>
  <div class="page" data-page="replay">
    <div class="panel row between">
      <n-select :value="id" :options="runOptions" filterable :placeholder="t('replay.pick')" style="max-width:520px" data-testid="replay-pick" @update:value="(v) => $router.push('/replay/' + v)" />
      <n-button v-if="id" secondary @click="$router.push('/report/' + id)">{{ t('replay.report') }}</n-button>
    </div>

    <div v-if="!id" class="panel empty"><div class="big">{{ t('replay.none') }}</div><p>{{ t('replay.noneHint') }}</p></div>
    <div v-else-if="err" class="panel" role="alert" data-testid="replay-error">{{ err }}</div>
    <div v-else-if="!loaded" class="panel empty"><n-spin /></div>
    <template v-else>
      <p class="hint">{{ t('replay.limit') }}</p>
      <div v-if="!fights.length" class="panel empty" data-testid="replay-empty">{{ t('replay.noFights') }}</div>
      <div v-else class="split">
        <div class="panel">
          <h3>{{ t('replay.fights') }}</h3>
          <button v-for="f in ordered" :key="f.index" type="button" class="item" :class="{ on: fight === f.index }" :data-fight="f.index" :data-trace="f.trace" @click="openFight(f.index)">
            <span class="nm">{{ f.enc_name || f.encounter || t('replay.fightN', { n: f.index + 1 }) }}</span>
            <span class="sb">{{ t('replay.result.' + (f.result || 'unknown')) }} · {{ t('replay.trace.' + f.trace) }}</span>
          </button>
        </div>
        <div class="panel" data-testid="replay-detail">
          <div v-if="!detail" class="hint">{{ t('replay.choose') }}</div>
          <template v-else>
            <h3>{{ detail.enc_name || detail.encounter }}</h3>
            <p class="hint">{{ detail.deck }} · {{ t('replay.result.' + (detail.result || 'unknown')) }}</p>
            <div v-if="detail.status !== 'ready'" class="note" role="status" data-testid="replay-status">{{ t('replay.why.' + detail.status) }}</div>
            <template v-else>
              <p v-if="detail.trace && detail.trace.truncated" class="note" data-testid="replay-truncated">{{ t('replay.truncated') }}</p>
              <p class="note" data-testid="replay-loss">{{ t('replay.lossTurn', { n: detail.trace.loss_turn }) }}</p>
              <ol class="tl">
                <li v-for="(ev, i) in (detail.trace && detail.trace.events) || []" :key="i" :data-kind="ev.kind" :data-hp-zero="ev.hp_zero ? '1' : '0'">
                  <span class="turn">{{ ev.turn ? t('replay.turn', { n: ev.turn }) : t('replay.start') }}</span>
                  <span>{{ line(ev) }}</span>
                  <span v-if="ev.hp_zero" class="zero">{{ t('replay.hpZero') }}</span>
                </li>
              </ol>
            </template>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NSelect, NSpin } from 'naive-ui'
import { api, store, fmt, runTitle } from '../api'
import { t } from '../i18n'

const route = useRoute()
const router = useRouter()
const id = computed(() => route.params.id || '')
const fights = ref([])
const fight = ref(null)
const detail = ref(null)
const err = ref('')
const loaded = ref(false)

const runOptions = computed(() => store.runs
  .filter((r) => r.kind === 'combat' && (r.status === 'done' || r.status === 'cancelled'))
  .map((r) => ({ label: `${runTitle(r)} · ${fmt.time(r.created)}`, value: r.id })))
const ordered = computed(() => [...fights.value].sort((a, b) => {
  if (a.trace === 'ready' && b.trace !== 'ready') return -1
  if (b.trace === 'ready' && a.trace !== 'ready') return 1
  return a.index - b.index
}))

function line(ev) {
  if (ev.kind === 'turn_start') return stateLine(ev.state)
  if (ev.kind === 'play') return t('replay.ev.play', { name: ev.name || ev.card, target: ev.target || t('replay.noTarget'), paid: ev.paid, energy: ev.energy })
  if (ev.kind === 'damage') return t('replay.ev.damage', { src: ev.src || t('replay.noSrc'), target: ev.target, amount: ev.amount, blocked: ev.blocked, lost: ev.lost, hp: ev.hp_after })
  if (ev.kind === 'hp_loss') return t('replay.ev.hpLoss', { target: ev.target, lost: ev.lost, hp: ev.hp_after })
  if (ev.kind === 'block') return t('replay.ev.block', { target: ev.target, amount: ev.amount, block: ev.block_after })
  if (ev.kind === 'power') return t('replay.ev.power', { target: ev.target, power: ev.power, delta: ev.delta, total: ev.total })
  if (ev.kind === 'power_blocked') return t('replay.ev.blocked', { target: ev.target, power: ev.power })
  if (ev.kind === 'enemy') return t('replay.ev.enemy', { name: ev.name, move: ev.move_name || ev.move || t('replay.noMove'), skipped: ev.skipped ? t('replay.skip.' + ev.skipped) : t('replay.skip.none') })
  if (ev.kind === 'potion') return t('replay.ev.potion', { name: ev.name })
  if (ev.kind === 'end') return t('replay.ev.end', { result: t('replay.result.' + (ev.result || 'unknown')) })
  return ev.kind
}
function stateLine(state) {
  const player = (state && state.player) || {}
  const foes = ((state && state.enemies) || []).map((e) => t('replay.foe', { name: e.name, hp: e.hp, block: e.block })).join(' · ')
  return t('replay.ev.state', { hp: player.hp, block: player.block, energy: player.energy, foes: foes || t('replay.noFoes') })
}
async function loadList() {
  loaded.value = false
  err.value = ''
  detail.value = null
  fights.value = []
  if (!id.value) {
    loaded.value = true
    return
  }
  try {
    const body = await api.get('/api/runs/' + encodeURIComponent(id.value) + '/fights')
    fights.value = body.fights || []
    const ready = fights.value.find((row) => row.trace === 'ready')
    const loss = fights.value.find((row) => row.result === 'loss')
    const pick = ready || loss || fights.value[0]
    if (pick) await openFight(pick.index)
  } catch (e) {
    err.value = e.message
  } finally {
    loaded.value = true
  }
}
async function openFight(index) {
  fight.value = index
  detail.value = null
  try {
    detail.value = await api.get('/api/runs/' + encodeURIComponent(id.value) + '/trace/' + index)
  } catch (e) {
    err.value = e.message
  }
}
onMounted(() => { store.loadRuns().catch(() => {}) })
watch(id, loadList, { immediate: true })
void router
</script>

<style scoped>
.split { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px; }
.item { display: flex; flex-direction: column; align-items: flex-start; width: 100%; text-align: left; background: transparent; border: 0; color: inherit; padding: 8px; border-radius: 8px; cursor: pointer; }
.item.on, .item:hover { background: #24242A; }
.nm { font-size: 13px; }
.sb { font-size: 11px; color: #77736C; }
.note { background: #26262B; border-radius: 8px; padding: 10px 12px; font-size: 13px; }
.tl { margin: 12px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.tl li { display: flex; flex-wrap: wrap; gap: 8px; font-size: 13px; line-height: 1.45; }
.turn { color: #F0A486; font-variant-numeric: tabular-nums; min-width: 4.5em; }
.zero { color: #E06C6C; font-weight: 650; }
</style>
