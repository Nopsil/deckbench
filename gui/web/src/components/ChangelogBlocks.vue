<template>
  <div class="notes">
    <template v-for="(block, i) in blocks" :key="i">
      <h2 v-if="block.kind === 'h' && block.level <= 2"><Spans :spans="block.spans" /></h2>
      <h3 v-else-if="block.kind === 'h' && block.level === 3"><Spans :spans="block.spans" /></h3>
      <h4 v-else-if="block.kind === 'h'"><Spans :spans="block.spans" /></h4>
      <p v-else-if="block.kind === 'p'"><Spans :spans="block.spans" /></p>
      <pre v-else-if="block.kind === 'pre'">{{ block.text }}</pre>
      <ul v-else-if="block.kind === 'ul'">
        <li v-for="(item, j) in block.items" :key="j">
          <ChangelogBlocks :blocks="item.blocks" />
        </li>
      </ul>
    </template>
  </div>
</template>

<script setup>
import Spans from './Spans.vue'

defineProps({
  blocks: { type: Array, default: () => [] },
})
</script>
