<template>
  <div class="panel p-5 animate-fade-slide group">
    <div class="flex items-start justify-between mb-3">
      <span class="data-label">{{ label }}</span>
      <span class="text-lg shrink-0">{{ icon }}</span>
    </div>
    <div class="flex items-baseline gap-1.5 mb-2">
      <span class="text-3xl font-mono font-semibold text-data-highlight tabular-nums">{{ formattedValue }}</span>
      <span v-if="unit" class="text-sm text-data-muted font-medium">{{ unit }}</span>
    </div>
    <div v-if="trend !== undefined" class="flex items-center gap-1.5">
      <span
        :class="[
          'text-xs font-mono font-medium',
          trend > 0 ? 'text-accent-green' : trend < 0 ? 'text-accent-red' : 'text-data-muted',
        ]"
      >
        {{ trend > 0 ? '▲' : trend < 0 ? '▼' : '—' }}
        {{ Math.abs(trend) }}%
      </span>
      <span class="text-[10px] text-data-muted">vs 上次</span>
    </div>
    <!-- 底部微光条 -->
    <div
      :class="['h-0.5 mt-3 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300', accentBar]"
    />
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  label: string
  value: number | string
  unit?: string
  icon?: string
  trend?: number
  accent?: 'blue' | 'cyan' | 'green' | 'amber' | 'purple'
}>(), {
  unit: '',
  icon: '📊',
  trend: undefined,
  accent: 'blue',
})

const formattedValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString()
  }
  return props.value
})

const accentBar = computed(() => ({
  blue: 'bg-accent-blue/50',
  cyan: 'bg-accent-cyan/50',
  green: 'bg-accent-green/50',
  amber: 'bg-accent-amber/50',
  purple: 'bg-accent-purple/50',
}[props.accent]))
</script>
