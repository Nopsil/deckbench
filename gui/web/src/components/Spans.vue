<template>
  <template v-for="(span, i) in spans" :key="i">
    <strong v-if="span.t === 'strong'"><Spans :spans="span.c" /></strong>
    <em v-else-if="span.t === 'em'"><Spans :spans="span.c" /></em>
    <code v-else-if="span.t === 'code'">{{ span.s }}</code>
    <a v-else-if="span.t === 'link'" :href="span.href" :target="external(span.href) ? '_blank' : undefined" rel="noopener noreferrer"><Spans :spans="span.c" /></a>
    <template v-else>{{ span.s }}</template>
  </template>
</template>

<script setup>
defineProps({
  spans: { type: Array, default: () => [] },
})

function external(href) {
  return typeof href === 'string' && (href.startsWith('https://') || href.startsWith('http://'))
}
</script>
