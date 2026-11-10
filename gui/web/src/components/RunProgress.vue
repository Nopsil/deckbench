<template>
  <div class="live" data-progress :data-status="view.status || ''" :data-partial="partial ? '1' : '0'">
    <div class="row between">
      <div class="label">{{ t('run.progressTitle') }}</div>
      <span class="state">{{ statusText }}</span>
    </div>
    <div class="track" data-progress-bar>
      <div class="fill" :class="view.status" :style="{ width: pct + '%' }"></div>
    </div>
    <div class="counts">
      <span data-progress-done>{{ view.done }}</span>
      <span class="sep">/</span>
      <span data-progress-total>{{ view.total }}</span>
    </div>
    <div class="line">
      <span class="faint">{{ t('run.encounter') }}</span>
      <b data-progress-encounter :data-encounter="view.encounter || ''">{{ encounterText }}</b>
    </div>
    <div class="line">
      <span class="faint">{{ t('common.elapsed') }}</span>
      <b data-progress-elapsed>{{ elapsedText }}</b>
    </div>
    <div v-if="partial" class="hint"><b>{{ t('run.partial') }}.</b> {{ t('run.partialHint') }}</div>
    <div v-else-if="view.cancel_requested" class="hint">{{ t('run.stopping') }}</div>
    <div v-if="err" class="hint warn">{{ err }}</div>
    <n-button
      v-if="cancellable && view.status === 'running'"
      secondary
      type="error"
      block
      data-action="cancel"
      :loading="cancelling"
      :disabled="view.cancel_requested"
      @click="cancel"
    >{{ t('run.cancel') }}</n-button>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { NButton } from 'naive-ui'
import { api, fmt } from '../api'
import { t } from '../i18n'

const props = defineProps({
  runId: { type: String, required: true },
  cancellable: { type: Boolean, default: true },
})
const emit = defineEmits(['update', 'settle'])

const view = ref({ done: 0, total: 0, status: 'running', encounter: '', encounter_name: '', elapsed: null, partial: false, cancel_requested: false })
const err = ref('')
const cancelling = ref(false)
let timer = null
let settled = false

const partial = computed(() => view.value.partial || view.value.status === 'cancelled')
const pct = computed(() => (view.value.total ? Math.min(100, 100 * view.value.done / view.value.total) : 0))
const encounterText = computed(() => view.value.encounter_name || view.value.encounter || '—')
const elapsedText = computed(() => fmt.secs(view.value.elapsed))
const statusText = computed(() => {
  const key = 'status.' + (view.value.status || 'running')
  const text = t(key)
  return text === key ? (view.value.status || '') : text
})

function stop() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function poll() {
  if (!props.runId) return
  try {
    const next = await api.get('/api/runs/' + encodeURIComponent(props.runId) + '/progress')
    view.value = next
    err.value = ''
    emit('update', next)
    if (next.status && next.status !== 'running' && next.status !== 'queued' && !settled) {
      settled = true
      stop()
      emit('settle', next)
    }
  } catch (e) {
    err.value = e.message
  }
}

function restart() {
  stop()
  settled = false
  err.value = ''
  view.value = { done: 0, total: 0, status: 'running', encounter: '', encounter_name: '', elapsed: null, partial: false, cancel_requested: false }
  poll()
  timer = setInterval(poll, 400)
}

async function cancel() {
  cancelling.value = true
  try {
    await api.post('/api/runs/' + encodeURIComponent(props.runId) + '/cancel')
    await poll()
  } catch (e) {
    err.value = e.message
  } finally {
    cancelling.value = false
  }
}

watch(() => props.runId, restart, { immediate: true })
onUnmounted(stop)
</script>

<style scoped>
.live { display: flex; flex-direction: column; gap: 8px; margin-top: 14px; }
.row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.state { font-size: 12px; color: #F0A486; font-weight: 650; }
.track { height: 10px; border-radius: 99px; background: #26262B; overflow: hidden; }
.fill { height: 100%; border-radius: 99px; background: linear-gradient(90deg, #C4664A, #E8946F); transition: width .3s ease; }
.fill.done { background: linear-gradient(90deg, #6FA36B, #8FBF8F); }
.fill.cancelled, .fill.failed, .fill.interrupted { background: #5A5A62; }
.counts { font-size: 22px; font-weight: 700; color: #F0A486; }
.sep { margin: 0 4px; color: #8A857E; font-weight: 500; }
.line { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
.line b { font-weight: 550; text-align: right; color: #E4DFD8; word-break: break-all; }
.faint { color: #8A857E; }
.hint { font-size: 12.5px; color: #B9B4AC; line-height: 1.45; }
.hint.warn { color: #E0A86C; }
</style>
