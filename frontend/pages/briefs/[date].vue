<script setup lang="ts">
/**
 * 单日简报详情页
 */
import type { DailyBrief } from '~/types'

const route = useRoute()
const { getBrief, getBriefPdfUrl } = useApi()

const date = computed(() => route.params.date as string)
const runId = computed(() => (route.query.run_id as string) || '')

const cacheKey = computed(() => `brief-${date.value}-${runId.value || 'latest'}`)

const { data, error, pending, refresh } = await useAsyncData(
  cacheKey.value,
  () => getBrief(date.value, runId.value).catch((err) => {
    console.error(`获取简报 ${date.value} 失败:`, err)
    return { brief: null }
  })
)

const brief = computed<DailyBrief | null>(() => data.value?.brief || null)
const pdfUrl = computed(() => getBriefPdfUrl(date.value))

function downloadPdf() {
  window.open(pdfUrl.value, '_blank')
}
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between animate-fade-slide">
      <div>
        <NuxtLink to="/briefs" class="text-xs text-accent-blue hover:text-accent-cyan transition-colors mb-2 inline-block">
          ← 返回列表
        </NuxtLink>
        <h1 class="text-2xl font-display text-data-highlight">每日简报</h1>
        <p class="text-sm text-data-muted font-mono">{{ date }}</p>
      </div>
      <button
        class="px-4 py-2 rounded-lg bg-terminal-hover border border-terminal-border text-sm font-medium text-data-text hover:border-accent-blue/30 transition-all"
        @click="downloadPdf"
      >
        📥 下载 PDF
      </button>
    </div>

    <!-- 加载中 -->
    <LoadingSpinner v-if="pending" text="加载简报内容..." />

    <!-- 错误 -->
    <EmptyState
      v-else-if="error"
      title="简报加载失败"
      :description="error?.message || `日期 ${date} 的简报不存在`"
      icon="⚠️"
      action-label="返回列表"
      @action="$router.push('/briefs')"
    />

    <!-- 简报内容 -->
    <template v-else-if="brief">
      <!-- 🔴 TOP5 要闻 -->
      <section class="panel p-6 animate-fade-slide stagger-1 opacity-0">
        <h2 class="text-lg font-semibold text-data-highlight mb-4 flex items-center gap-2">
          <span class="w-1 h-5 rounded-full bg-accent-red" />
          🔴 今日要闻 TOP5
        </h2>
        <div class="space-y-2">
          <div
            v-for="(item, i) in brief.top_news"
            :key="i"
            class="flex items-start gap-3 p-3 rounded-lg bg-terminal-hover/50 border border-terminal-border"
          >
            <span
              class="text-lg font-bold font-mono shrink-0 w-8"
              :class="i === 0 ? 'text-accent-amber' : 'text-data-muted'"
            >
              #{{ i + 1 }}
            </span>
            <div>
              <div class="text-sm font-medium text-data-highlight">{{ item.title }}</div>
              <div class="text-[10px] text-data-muted mt-0.5">
                {{ '⭐'.repeat(item.importance || 1) }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 📝 深度研报 -->
      <section class="panel p-6 animate-fade-slide stagger-2 opacity-0">
        <h2 class="text-lg font-semibold text-data-highlight mb-4 flex items-center gap-2">
          <span class="w-1 h-5 rounded-full bg-accent-blue" />
          📝 深度研报
        </h2>
        <div class="space-y-4">
          <div
            v-for="(r, i) in brief.research_reports"
            :key="i"
            class="p-4 rounded-lg bg-terminal-hover/50 border border-terminal-border"
          >
            <h3 class="text-sm font-semibold text-data-highlight mb-2">{{ r.title }}</h3>
            <p class="text-xs text-data-muted leading-relaxed">
              {{ r.summary || '暂无摘要' }}
            </p>
          </div>
        </div>
      </section>

      <!-- 🏭 行业动态 -->
      <section v-if="brief.industry_briefs.length > 0" class="panel p-6 animate-fade-slide stagger-3 opacity-0">
        <h2 class="text-lg font-semibold text-data-highlight mb-4 flex items-center gap-2">
          <span class="w-1 h-5 rounded-full bg-accent-green" />
          🏭 行业动态
        </h2>
        <div class="overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="border-b border-terminal-border">
                <th class="text-left py-2 px-3 text-data-muted font-medium">行业/主题</th>
                <th class="text-left py-2 px-3 text-data-muted font-medium">动态</th>
                <th class="text-right py-2 px-3 text-data-muted font-medium">报道数</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, i) in brief.industry_briefs"
                :key="i"
                class="border-b border-terminal-border/50 hover:bg-terminal-hover/30 transition-colors"
              >
                <td class="py-2 px-3 font-medium text-data-text">{{ item.industry }}</td>
                <td class="py-2 px-3 text-data-muted">{{ item.summary }}</td>
                <td class="py-2 px-3 text-right font-mono text-accent-blue">{{ item.article_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 📉 数据看板 -->
      <section class="panel p-6 animate-fade-slide stagger-4 opacity-0">
        <h2 class="text-lg font-semibold text-data-highlight mb-4 flex items-center gap-2">
          <span class="w-1 h-5 rounded-full bg-accent-purple" />
          📉 数据看板
        </h2>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div
            v-for="(value, key) in brief.data_board"
            :key="key"
            class="text-center p-3 rounded-lg bg-terminal-hover/50 border border-terminal-border"
          >
            <div class="text-xs text-data-muted mb-1">{{ key }}</div>
            <div class="text-lg font-mono font-bold text-data-highlight">{{ value }}</div>
          </div>
        </div>
      </section>

      <!-- 🔮 明日关注 -->
      <section v-if="brief.tomorrow_focus.length > 0" class="panel p-6 animate-fade-slide stagger-5 opacity-0">
        <h2 class="text-lg font-semibold text-data-highlight mb-4 flex items-center gap-2">
          <span class="w-1 h-5 rounded-full bg-accent-cyan" />
          🔮 明日关注
        </h2>
        <div class="space-y-2">
          <div
            v-for="(item, i) in brief.tomorrow_focus"
            :key="i"
            class="flex items-center gap-2 text-sm text-data-text"
          >
            <span class="text-accent-amber text-xs">▶</span>
            {{ item }}
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
