<template>
  <aside
    :class="[
      'fixed inset-y-0 left-0 z-40 flex flex-col transition-all duration-300',
      'bg-terminal-surface border-r border-terminal-border',
      collapsed ? 'w-16' : 'w-60',
    ]"
  >
    <!-- Logo -->
    <NuxtLink
      to="/"
      class="flex items-center gap-3 h-14 px-4 border-b border-terminal-border shrink-0"
    >
      <div class="w-8 h-8 rounded bg-gradient-to-br from-accent-blue to-accent-cyan flex items-center justify-center text-white font-bold text-sm shrink-0">
        智
      </div>
      <span
        v-if="!collapsed"
        class="font-display text-lg text-data-highlight tracking-wide"
      >
        智览
      </span>
    </NuxtLink>

    <!-- 导航 -->
    <nav class="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
      <NavItem
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :icon="item.icon"
        :label="item.label"
        :collapsed="collapsed"
      />
    </nav>

    <!-- 底部：状态 + 折叠 -->
    <div class="p-2 border-t border-terminal-border space-y-2">
      <div
        v-if="!collapsed"
        class="flex items-center gap-2 px-3 py-1.5 text-xs text-data-muted"
      >
        <span class="status-dot" :class="backendOnline ? 'status-dot-active' : 'status-dot-error'" />
        <span>{{ backendOnline ? '后端已连接' : '后端离线' }}</span>
      </div>

      <button
        class="w-full flex items-center justify-center p-2 rounded text-data-muted hover:text-data-text hover:bg-terminal-hover transition-colors"
        @click="collapsed = !collapsed"
      >
        <svg
          :class="['w-5 h-5 transition-transform duration-300', collapsed && 'rotate-180']"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
        </svg>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
const collapsed = ref(false)
const backendOnline = ref(false)

const { getStatus } = useApi()
onMounted(async () => {
  const check = async () => {
    try {
      const res = await getStatus()
      backendOnline.value = res.healthy
    } catch {
      backendOnline.value = false
    }
  }
  await check()
  setInterval(check, 30000)
})

const navItems = [
  { to: '/', icon: '◈', label: '工作台' },
  { to: '/briefs', icon: '◆', label: '每日简报' },
  { to: '/clusters', icon: '◇', label: '聚类分析' },
  { to: '/monitor', icon: '▷', label: '实时监控' },
  { to: '/settings', icon: '⚙', label: '系统配置' },
]
</script>
