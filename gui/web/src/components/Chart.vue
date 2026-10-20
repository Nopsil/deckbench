<template>
  <v-chart class="chart" :option="option" :style="{ height: height + 'px' }" autoresize />
</template>
<script setup>
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart, CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DataZoomComponent } from 'echarts/components'
import VChart from 'vue-echarts'
use([CanvasRenderer, LineChart, BarChart, PieChart, CustomChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DataZoomComponent])
defineProps({ option: Object, height: { type: Number, default: 300 } })
</script>
<style scoped>.chart { width: 100%; }</style>
