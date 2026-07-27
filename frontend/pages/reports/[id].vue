<script setup lang="ts">
/**
 * 研报详情页 — 结构化四段式展示
 */
import type { ReportFullResponse } from '~/types'

const route = useRoute()
const { getReport } = useApi()

const reportId = computed(() => route.params.id as string)

const { data, error, pending, refresh } = await useAsyncData(
  `report-${reportId.value}`,
  () => getReport(reportId.value)
)

const report = computed(() => data.value?.report || null)
const review = computed(() => data.value?.review || null)
const cluster = computed(() => data.value?.cluster || null)

const sections = [
  { key: 'background', title: '一、事件背景', icon: '📖', color: 'bg-accent-blue' },
  { key: 'analysis', title: '二、现状分析', icon: '📊', color: 'bg-accent-cyan' },
  { key: 'outlook', title: '三、趋势研判', icon: '📈', color: 'bg-accent-amber' },
  { key: 'risk', title: '四、风险提示', icon: '⚠️', color: 'bg-accent-red' },
]

const expandedSections = ref<Record<string, boolean>>({
  background: true,
  analysis: true,
  outlook: true,
  risk: true,
})

function toggleSection(key: string) {
  expandedSections.value[key] = !expandedSections.value[key]
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- 返回导航 -->
    <NuxtLink to="/" class="text-xs text-accent-blue hover:text-accent-cyan transition-colors inline-block animate-fade-slide">
      ← 返回工作台
    </NuxtLink>

    <!-- 加载中 -->
    <LoadingSpinner v-if="pending" text="加载研报..." />

    <!-- 错误 -->
    <EmptyState
      v-else-if="error"
      title="研报加载失败"
      :description="error?.message || '研报不存在'"
      icon="⚠️"
      action-label="返回工作台"
      @action="$router.push('/')"
    />

    <!-- 研报内容 -->
    <template v-else-if="report">
      <!-- 头部 -->
      <section class="panel p-6 animate-fade-slide">
        <div class="flex items-start justify-between mb-4">
          <div>
            <h1 class="text-xl font-display text-data-highlight mb-2">{{ report.title }}</h1>
            <div class="flex items-center gap-3 text-xs text-data-muted">
              <span class="font-mono">ID: {{ report.report_id }}</span>
              <span v-if="cluster" class="text-accent-blue">{{ cluster.label }}</span>
              <span>重要度: {{ cluster?.importance || '-' }}/10</span>
            </div>
          </div>
          <StatusBadge
            v-if="review"
            :status="review.passed ? 'success' : 'warning'"
          >
            {{ review.passed ? '审核通过' : '需修改' }}
          </StatusBadge>
        </div>

        <!-- 审核建议 -->
        <div
          v-if="review && !review.passed && review.suggestions.length > 0"
          class="mt-4 p-3 rounded-lg bg-accent-amber/5 border border-accent-amber/20"
        >
          <div class="text-xs font-medium text-accent-amber mb-1">审核建议：</div>
          <ul class="text-xs text-data-muted space-y-1">
            <li v-for="(s, i) in review.suggestions" :key="i">• {{ s }}</li>
          </ul>
        </div>
      </section>

      <!-- 四段式研报 -->
      <section
        v-for="(sec, i) in sections"
        :key="sec.key"
        :class="[
          'panel overflow-hidden animate-fade-slide opacity-0',
          `stagger-${i + 1}`,
        ]"
      >
        <button
          class="w-full flex items-center justify-between p-5 hover:bg-terminal-hover/50 transition-colors"
          @click="toggleSection(sec.key)"
        >
          <div class="flex items-center gap-3">
            <span class="w-1 h-5 rounded-full" :class="sec.color" />
            <span class="text-lg">{{ sec.icon }}</span>
            <h2 class="text-base font-semibold text-data-highlight">{{ sec.title }}</h2>
          </div>
          <svg
            :class="['w-5 h-5 text-data-muted transition-transform duration-200', expandedSections[sec.key] && 'rotate-180']"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        <div
          v-if="expandedSections[sec.key]"
          class="px-5 pb-5"
        >
          <div class="prose prose-invert max-w-none">
            <p class="text-sm text-data-text leading-relaxed whitespace-pre-line">
              {{ (report as any)[sec.key] || '暂无内容' }}
            </p>
          </div>
        </div>
      </section>

      <!-- 元数据 -->
      <section class="panel p-5 animate-fade-slide stagger-5 opacity-0">
        <h3 class="data-label mb-3">📋 生成信息</h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <span class="text-data-muted">模型</span>
            <div class="text-data-text font-mono mt-0.5">{{ report.model_used || '-' }}</div>
          </div>
          <div>
            <span class="text-data-muted">生成时间</span>
            <div class="text-data-text font-mono mt-0.5">{{ report.generated_at ? new Date(report.generated_at).toLocaleString('zh-CN') : '-' }}</div>
          </div>
          <div>
            <span class="text-data-muted">检索文档</span>
            <div class="text-data-text font-mono mt-0.5">{{ report.rag_info?.docs_retrieved || '-' }}</div>
          </div>
          <div>
            <span class="text-data-muted">Rerank 后</span>
            <div class="text-data-text font-mono mt-0.5">{{ report.rag_info?.docs_reranked || '-' }}</div>
          </div>
        </div>
      </section>

      <!-- 引用来源 -->
      <section v-if="report.references.length > 0" class="panel p-5 animate-fade-slide stagger-6 opacity-0">
        <h3 class="data-label mb-3">📚 引用来源</h3>
        <div class="space-y-2">
          <div
            v-for="(ref, i) in report.references"
            :key="i"
            class="flex items-center gap-2 text-xs p-2 rounded bg-terminal-hover/50"
          >
            <span class="text-data-muted shrink-0">[{{ i + 1 }}]</span>
            <a
              v-if="ref.url"
              :href="ref.url"
              target="_blank"
              class="text-accent-blue hover:text-accent-cyan transition-colors truncate"
            >
              {{ ref.title || ref.url }}
            </a>
            <span v-else class="text-data-text truncate">{{ ref.title }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
