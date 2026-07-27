<script setup lang="ts">
/**
 * 每日简报 — 列表页（也是 /briefs/* 子路由的父布局）
 *
 * Nuxt 3 文件路由约定：
 * - pages/briefs/index.vue → /briefs（本文件）
 * - pages/briefs/[date].vue → /briefs/:date
 *
 * index.vue 是 briefs/ 目录下所有子路由的布局组件，
 * 必须包含 <NuxtPage /> 才能渲染子页面。
 */
import type { BriefListItem } from '~/types'

const route = useRoute()
const { getBriefList } = useApi()

// 仅在 /briefs（非子路由）时显示列表
const isListRoute = computed(() => !route.params.date)

const { data, error, pending, refresh } = await useAsyncData(
  'briefs-list',
  () => getBriefList().catch((err) => {
    console.error('获取简报列表失败:', err)
    return { dates: [], latest_date: null }
  })
)

const dates = computed<BriefListItem[]>(() => data.value?.dates || [])
const latestDate = computed(() => data.value?.latest_date)
</script>

<template>
  <!-- 列表视图：仅在 /briefs 时显示 -->
  <div v-if="isListRoute" class="max-w-5xl mx-auto space-y-6">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between animate-fade-slide">
      <div>
        <h1 class="text-2xl font-display text-data-highlight mb-1">每日简报</h1>
        <p class="text-sm text-data-muted">
          历史日报存档 · 共 {{ dates.length }} 份
        </p>
      </div>
      <NuxtLink
        v-if="latestDate"
        :to="`/briefs/${latestDate}`"
        class="px-4 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:shadow-lg hover:shadow-accent-blue/20 transition-all"
      >
        查看最新 →
      </NuxtLink>
    </div>

    <!-- 加载中 -->
    <LoadingSpinner v-if="pending" text="加载日报列表..." />

    <!-- 错误 -->
    <EmptyState
      v-else-if="error"
      title="加载失败"
      :description="error?.message || '无法连接后端服务'"
      icon="⚠️"
      action-label="重试"
      @action="refresh()"
    />

    <!-- 简报列表（同一天可有多份，用 run_id 区分） -->
    <div v-else-if="dates.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <NuxtLink
        v-for="(item, i) in dates"
        :key="`${item.date}-${item.run_id || i}`"
        :to="`/briefs/${item.date}${item.run_id ? '?run_id=' + item.run_id : ''}`"
        :class="[
          'panel-hover p-5 animate-fade-slide opacity-0',
          `stagger-${Math.min(i + 1, 6)}`,
          item.date === latestDate && i === 0 ? 'glow-border' : '',
        ]"
      >
        <div class="flex items-start justify-between mb-3">
          <div>
            <span class="text-xs text-accent-blue font-mono mb-1 block">
              {{ new Date(item.date).toLocaleDateString('zh-CN', { weekday: 'long' }) }}
            </span>
            <span class="text-xl font-mono font-bold text-data-highlight">
              {{ item.date }}
            </span>
          </div>
          <span
            v-if="i === 0"
            class="px-2 py-0.5 rounded text-[10px] font-medium bg-accent-blue/10 text-accent-blue border border-accent-blue/20"
          >
            Latest
          </span>
        </div>
        <div class="flex items-center gap-3 text-[10px] text-data-muted">
          <span class="font-mono">{{ item.size_bytes ? (item.size_bytes / 1024).toFixed(1) + ' KB' : '-' }}</span>
          <span>{{ new Date(item.generated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</span>
          <span v-if="item.run_id" class="font-mono text-accent-blue">#{{ item.run_id.slice(0, 6) }}</span>
        </div>
      </NuxtLink>
    </div>

    <!-- 空状态 -->
    <EmptyState
      v-else
      title="暂无日报"
      description="启动工作流生成你的第一份 AI 日报"
      icon="📰"
      action-label="前往工作台"
      @action="$router.push('/')"
    />
  </div>

  <!-- 子路由出口：/briefs/:date 的详情页在此渲染 -->
  <NuxtPage />
</template>
