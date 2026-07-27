<template>
  <div class="min-h-screen bg-terminal-bg text-data-text">
    <!-- 侧边栏 -->
    <AppSidebar />

    <!-- 主内容区 -->
    <div class="transition-all duration-300 ml-60" id="main-content">
      <!-- 顶部导航 -->
      <header class="sticky top-0 z-30 h-12 bg-terminal-bg/80 backdrop-blur-sm border-b border-terminal-border flex items-center px-6 gap-4">
        <div class="flex items-center gap-2 text-xs text-data-muted">
          <span class="text-accent-blue font-mono">{{ route.meta?.title || route.name || '智览' }}</span>
          <span class="text-terminal-border">/</span>
          <span class="text-data-text font-medium">{{ pageTitle }}</span>
        </div>
        <div class="ml-auto flex items-center gap-3 text-xs text-data-muted">
          <span class="font-mono">{{ now }}</span>
        </div>
      </header>

      <!-- 页面内容 -->
      <main class="p-6">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute()

const pageTitles: Record<string, string> = {
  '/': 'Dashboard 工作台',
  '/briefs': '每日简报',
  '/clusters': '聚类分析',
  '/monitor': '实时监控',
  '/settings': '系统配置',
}

const pageTitle = computed(() => {
  const base = route.path
  if (base.startsWith('/briefs/')) return '简报详情'
  if (base.startsWith('/reports/')) return '研报详情'
  return pageTitles[base] || base
})

const now = ref('')
const updateClock = () => {
  now.value = new Date().toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}
onMounted(() => {
  updateClock()
  setInterval(updateClock, 1000)
})
</script>
