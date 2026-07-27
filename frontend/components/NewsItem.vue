<template>
  <div class="panel-hover p-4 animate-fade-slide">
    <div class="flex items-start justify-between mb-2">
      <div class="flex items-center gap-2">
        <span
          class="text-lg font-bold font-mono text-accent-amber"
          :class="{ 'text-accent-green': index === 0 }"
        >
          #{{ index }}
        </span>
        <h4 class="text-sm font-medium text-data-highlight leading-snug">
          {{ item.title }}
        </h4>
      </div>
      <span class="text-[10px] font-mono text-data-muted shrink-0">
        {{ '⭐'.repeat(item.importance || 1) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TopNewsItem } from '~/types'

defineProps<{
  item: TopNewsItem
  index: number
}>()
</script>
