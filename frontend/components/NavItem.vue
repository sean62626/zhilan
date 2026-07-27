<template>
  <NuxtLink
    :to="to"
    :class="[
      'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200',
      isActive
        ? 'bg-accent-blue/10 text-accent-blue border border-accent-blue/20'
        : 'text-data-muted hover:text-data-text hover:bg-terminal-hover border border-transparent',
    ]"
  >
    <span class="text-lg shrink-0 w-6 text-center">{{ icon }}</span>
    <span v-if="!collapsed" class="text-sm font-medium truncate">{{ label }}</span>
    <span
      v-if="isActive"
      class="ml-auto w-1 h-4 rounded-full bg-accent-blue"
      :class="{ hidden: collapsed }"
    />
  </NuxtLink>
</template>

<script setup lang="ts">
const props = defineProps<{
  to: string
  icon: string
  label: string
  collapsed: boolean
}>()

const route = useRoute()
const isActive = computed(() => {
  if (props.to === '/') return route.path === '/'
  return route.path.startsWith(props.to)
})
</script>
