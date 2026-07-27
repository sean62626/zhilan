<template>
  <span
    :class="[
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium',
      variantClass,
    ]"
  >
    <span class="status-dot" :class="dotClass" />
    <slot />
  </span>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  status?: 'success' | 'warning' | 'error' | 'info' | 'neutral'
}>(), {
  status: 'neutral',
})

const variantClass = computed(() => ({
  success: 'bg-accent-green/10 text-accent-green border border-accent-green/20',
  warning: 'bg-accent-amber/10 text-accent-amber border border-accent-amber/20',
  error: 'bg-accent-red/10 text-accent-red border border-accent-red/20',
  info: 'bg-accent-blue/10 text-accent-blue border border-accent-blue/20',
  neutral: 'bg-terminal-hover text-data-muted border border-terminal-border',
}[props.status]))

const dotClass = computed(() => ({
  success: 'status-dot-active',
  warning: 'status-dot-warning',
  error: 'status-dot-error',
  info: 'bg-accent-blue rounded-full w-2 h-2',
  neutral: 'bg-data-muted rounded-full w-2 h-2',
}[props.status]))
</script>
