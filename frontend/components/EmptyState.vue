<template>
  <div class="panel p-10 text-center animate-fade-slide">
    <div class="text-4xl mb-4 opacity-50">{{ icon }}</div>
    <h3 class="text-lg font-medium text-data-text mb-2">{{ title }}</h3>
    <p class="text-sm text-data-muted max-w-md mx-auto">{{ description }}</p>
    <button
      v-if="actionLabel"
      class="mt-6 px-4 py-2 rounded-lg bg-accent-blue/10 text-accent-blue border border-accent-blue/20 hover:bg-accent-blue/20 transition-colors text-sm font-medium"
      @click="$emit('action')"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  icon?: string
  title: string
  description?: string
  actionLabel?: string
}>()

defineEmits<{
  action: []
}>()
</script>
