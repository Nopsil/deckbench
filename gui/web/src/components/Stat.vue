<template>
  <div class="stat" :class="{ hl }">
    <div class="k">{{ label }}</div>
    <div class="v">{{ value }}</div>
    <div v-if="sub" class="s">{{ sub }}</div>
    <div v-if="bar !== null && bar !== undefined" class="bar" :style="{ width: Math.max(0, Math.min(1, bar)) * 100 + '%' }"></div>
  </div>
</template>
<script setup>
defineProps({ label: String, value: [String, Number], sub: String, hl: Boolean, bar: { type: Number, default: null } })
</script>
