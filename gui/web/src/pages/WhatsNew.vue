<template>
  <div class="page" data-page="whatsnew">
    <div class="panel">
      <div v-if="error" class="empty" data-testid="whatsnew-missing"><div class="big">{{ t('whatsnew.missing') }}</div></div>
      <div v-else-if="!notes" class="empty"><n-spin /></div>
      <div v-else-if="!notes.blocks || !notes.blocks.length" class="empty" data-testid="whatsnew-empty"><div class="big">{{ t('whatsnew.empty') }}</div></div>
      <div v-else data-testid="whatsnew-notes">
        <h2 v-if="notes.heading" class="wn-heading">{{ notes.heading }}</h2>
        <ChangelogBlocks :blocks="notes.blocks" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { NSpin } from 'naive-ui'
import ChangelogBlocks from '../components/ChangelogBlocks.vue'
import { t } from '../i18n'

const notes = ref(null)
const error = ref(false)

onMounted(async () => {
  try {
    const res = await fetch('/api/changelog')
    if (!res.ok) {
      error.value = true
      return
    }
    notes.value = await res.json()
  } catch (e) {
    error.value = true
  }
})
</script>

<style scoped>
.wn-heading { margin: 0 0 14px; font-size: 18px; font-weight: 650; }
</style>
