<script setup lang="ts">
/**
 * 聚类分析页 — 主题簇可视化 + 列表
 */
import type { TopicCluster } from '~/types'

const { getClusters } = useApi()

const { data, error, pending, refresh } = await useAsyncData(
  'clusters-data',
  () => getClusters()
)

const clusters = computed<TopicCluster[]>(() => data.value?.clusters || [])
const totalArticles = computed(() => data.value?.total_articles || 0)
const dateDist = computed(() => data.value?.date_distribution || [])

// 选中的簇
const selectedCluster = ref<TopicCluster | null>(null)

const importanceClass = (score: number) => {
  if (score >= 8) return 'text-accent-red'
  if (score >= 6) return 'text-accent-amber'
  return 'text-accent-green'
}
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between animate-fade-slide">
      <div>
        <h1 class="text-2xl font-display text-data-highlight mb-1">聚类分析</h1>
        <p class="text-sm text-data-muted">
          语义聚类结果 · {{ clusters.length }} 个主题簇 · {{ totalArticles }} 篇文章
        </p>
      </div>
      <button
        class="px-3 py-1.5 rounded text-xs text-data-muted hover:text-data-text border border-terminal-border hover:border-accent-blue/30 transition-all"
        @click="refresh()"
      >
        🔄 刷新
      </button>
    </div>

    <!-- 加载中 -->
    <LoadingSpinner v-if="pending" text="加载聚类数据..." />

    <!-- 错误 -->
    <EmptyState
      v-else-if="error"
      title="加载失败"
      :description="error?.message || '无法获取聚类数据'"
      icon="⚠️"
      action-label="重试"
      @action="refresh()"
    />

    <template v-else-if="clusters.length > 0">
      <!-- 文章时间分布 -->
      <section v-if="dateDist.length > 0" class="panel p-5 animate-fade-slide">
        <h2 class="text-sm font-semibold text-data-highlight mb-4">📅 文章时间分布</h2>
        <div class="flex items-end gap-1 h-24">
          <div
            v-for="d in dateDist"
            :key="d.date"
            class="flex-1 flex flex-col items-center justify-end"
          >
            <div
              class="w-full rounded-t bg-accent-blue/60 hover:bg-accent-blue transition-colors"
              :style="{ height: Math.max(4, (d.count / Math.max(...dateDist.map(x => x.count))) * 100) + '%' }"
              :title="`${d.date}: ${d.count} 篇`"
            />
            <span class="text-[8px] text-data-muted mt-1 rotate-45 origin-left whitespace-nowrap">
              {{ d.date.slice(5) }}
            </span>
          </div>
        </div>
      </section>

      <!-- 簇列表 -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="(c, i) in clusters"
          :key="c.cluster_id"
          :class="[
            'panel-hover p-5 cursor-pointer animate-fade-slide opacity-0',
            `stagger-${Math.min(i + 1, 6)}`,
            selectedCluster?.cluster_id === c.cluster_id ? 'glow-border' : '',
          ]"
          @click="selectedCluster = selectedCluster?.cluster_id === c.cluster_id ? null : c"
        >
          <!-- 重要性评分 -->
          <div class="flex items-center justify-between mb-3">
            <span class="text-[10px] font-mono text-accent-blue">
              Cluster #{{ c.cluster_id }}
            </span>
            <span
              :class="['text-lg font-bold font-mono', importanceClass(c.importance)]"
            >
              {{ c.importance }}/10
            </span>
          </div>

          <!-- 标签 -->
          <h3 class="text-base font-semibold text-data-highlight mb-2">{{ c.label }}</h3>

          <!-- 关键词 -->
          <div class="flex flex-wrap gap-1 mb-3">
            <span
              v-for="kw in c.keywords"
              :key="kw"
              class="px-2 py-0.5 rounded text-[10px] font-medium bg-terminal-hover text-data-muted border border-terminal-border"
            >
              {{ kw }}
            </span>
          </div>

          <!-- 统计 -->
          <div class="flex items-center gap-4 text-[10px] text-data-muted">
            <span>{{ c.article_count }} 篇文章</span>
            <span v-if="c.representative_title" class="truncate">
              📌 {{ c.representative_title.slice(0, 40) }}...
            </span>
          </div>

          <!-- 展开：文章列表 -->
          <div
            v-if="selectedCluster?.cluster_id === c.cluster_id && c.articles.length > 0"
            class="mt-4 pt-4 border-t border-terminal-border space-y-1 max-h-60 overflow-y-auto"
          >
            <div
              v-for="a in c.articles"
              :key="a.id"
              class="flex items-center gap-2 text-xs py-1"
            >
              <span class="text-data-muted shrink-0">•</span>
              <span class="text-data-text truncate">{{ a.title }}</span>
              <span class="text-data-muted shrink-0 text-[10px]">{{ a.source_name }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 空状态 -->
    <EmptyState
      v-else
      title="暂无聚类数据"
      description="启动工作流完成文章采集和聚类分析"
      icon="🔗"
      action-label="前往工作台"
      @action="$router.push('/')"
    />
  </div>
</template>
