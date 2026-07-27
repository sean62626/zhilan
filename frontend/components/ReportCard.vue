<template>
  <NuxtLink
    :to="`/reports/${report.report_id}`"
    class="panel-hover p-4 block animate-fade-slide"
  >
    <div class="flex items-start justify-between mb-2">
      <h4 class="text-sm font-semibold text-data-highlight leading-snug line-clamp-2 flex-1">
        {{ report.title }}
      </h4>
      <StatusBadge
        :status="report.review_passed ? 'success' : 'warning'"
        class="ml-2 shrink-0"
      >
        {{ report.review_passed ? '已审核' : '待修改' }}
      </StatusBadge>
    </div>
    <p class="text-xs text-data-muted line-clamp-2 mb-3">
      {{ report.background_preview || '暂无摘要' }}
    </p>
    <div class="flex items-center gap-3 text-[10px] text-data-muted">
      <span class="font-mono">ID: {{ report.report_id }}</span>
      <span v-if="report.model_used" class="text-accent-blue">{{ report.model_used }}</span>
      <span v-if="report.generated_at" class="ml-auto">
        {{ new Date(report.generated_at).toLocaleString('zh-CN') }}
      </span>
    </div>
  </NuxtLink>
</template>

<script setup lang="ts">
import type { ReportSummary } from '~/types'

defineProps<{
  report: ReportSummary
}>()
</script>
