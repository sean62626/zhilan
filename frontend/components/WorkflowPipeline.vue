<template>
  <div class="panel p-5 animate-fade-slide">
    <h3 class="data-label mb-4">工作流管道</h3>
    <div class="space-y-2">
      <div
        v-for="(node, i) in nodes"
        :key="node.key"
        class="flex items-center gap-3"
      >
        <!-- 节点指示器 -->
        <div class="flex flex-col items-center">
          <div
            :class="[
              'w-8 h-8 rounded-lg flex items-center justify-center text-xs font-mono font-bold transition-all duration-300',
              nodeStatus(node.key),
            ]"
          >
            {{ i + 1 }}
          </div>
          <div
            v-if="i < nodes.length - 1"
            :class="[
              'w-0.5 h-4 mt-0.5 transition-colors duration-300',
              isNodeDone(node.key) ? 'bg-accent-green' : 'bg-terminal-border',
            ]"
          />
        </div>

        <!-- 节点信息 -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-data-text">{{ node.label }}</span>
            <span
              v-if="currentNode === node.key && status === 'running'"
              class="text-[10px] text-accent-blue animate-pulse"
            >
              执行中...
            </span>
            <span
              v-else-if="isNodeDone(node.key)"
              class="text-[10px] text-accent-green"
            >
              完成
            </span>
          </div>
          <div class="text-[10px] text-data-muted mt-0.5">{{ node.desc }}</div>
          <!-- 当前节点详细进度 — 醒目的蓝色提示条 -->
          <div
            v-if="currentNode === node.key && progressMessage && status === 'running'"
            class="mt-2 py-1.5 px-3 rounded-md bg-accent-blue/10 border border-accent-blue/30 text-[11px] text-accent-blue font-medium leading-relaxed animate-pulse"
          >
            {{ progressMessage }}
          </div>
        </div>

        <!-- 状态图标 -->
        <span class="shrink-0 text-sm">
          <span v-if="isNodeDone(node.key)">✅</span>
          <span v-else-if="currentNode === node.key && status === 'running'">⏳</span>
          <span v-else>◯</span>
        </span>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="mt-4">
      <div class="flex justify-between text-[10px] text-data-muted mb-1">
        <span>
          <template v-if="status === 'cancelled'">⏹ 已取消 · </template>
          {{ progress }}%
        </span>
        <span>{{ completedNodes }}/{{ nodes.length }} 节点</span>
      </div>
      <div class="h-1.5 rounded-full bg-terminal-hover overflow-hidden">
        <div
          :class="[
            'h-full rounded-full transition-all duration-500',
            status === 'completed' ? 'bg-accent-green' :
            status === 'cancelled' ? 'bg-accent-amber' :
            'gradient-progress',
          ]"
          :style="{ width: progress + '%' }"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useWorkflowStore } from '~/stores/workflow'
import { storeToRefs } from 'pinia'

/**
 * 直接从 Pinia store 读取工作流状态，而非依赖父组件 props 传递。
 *
 * 原因：父组件 index.vue 是异步组件（含 top-level await），在 WebSocket 事件密集到达时
 * 可能出现渲染调度延迟，导致子组件无法及时收到更新 props。
 * 直接订阅 store 可绕过父组件的重渲染链路，确保状态变化立即反映到 UI。
 */
const workflowStore = useWorkflowStore()
const { nodesCompleted, status, currentNode, progressMessage } = storeToRefs(workflowStore)

// 保留 props 定义以保持 API 向后兼容（其他组件可能直接传 props），
// 但组件内部所有响应式绑定均使用上面解构的 store refs。
const props = withDefaults(defineProps<{
  nodesCompleted: string[]
  status: string
  currentNode?: string | null
  progressMessage?: string | null
}>(), {
  nodesCompleted: () => [],
  status: 'idle',
  currentNode: null,
  progressMessage: null,
})

const nodes = [
  { key: 'collect', label: 'Collect 采集', desc: '多源数据采集' },
  { key: 'preprocess', label: 'Preprocess 预处理', desc: '文本清洗与标准化' },
  { key: 'dedup', label: 'Dedup 去重', desc: '三层去重过滤' },
  { key: 'cluster', label: 'Cluster 聚类', desc: '语义聚类 + 标签' },
  { key: 'research', label: 'Research 研报', desc: 'RAG 深度摘要' },
  { key: 'review', label: 'Review 审核', desc: '事实核查 + 幻觉检测' },
  { key: 'compose', label: 'Compose 组装', desc: '日报组装' },
  { key: 'export', label: 'Export 导出', desc: 'MD / PDF 导出' },
]

const completedNodes = computed(() =>
  nodesCompleted.value.filter((n) => nodes.some((nd) => nd.key === n)).length
)

const progress = computed(() => {
  if (status.value === 'completed') return 100
  if (status.value === 'cancelled') {
    return Math.round((completedNodes.value / nodes.length) * 100)
  }
  return Math.round((completedNodes.value / nodes.length) * 100)
})

function isNodeDone(key: string): boolean {
  return nodesCompleted.value.includes(key) || status.value === 'completed' || status.value === 'cancelled'
}

function nodeStatus(key: string): string {
  // 取消状态：已完成的节点显示为琥珀色
  if (status.value === 'cancelled' && isNodeDone(key)) {
    return 'bg-accent-amber/20 text-accent-amber border border-accent-amber/30'
  }
  // 已完成状态或已完成的节点：绿色
  if (nodesCompleted.value.includes(key)) {
    return 'bg-accent-green/20 text-accent-green border border-accent-green/30'
  }
  if (status.value === 'completed') {
    return 'bg-accent-green/20 text-accent-green border border-accent-green/30'
  }
  // 当前正在执行的节点：蓝色脉冲（使用从 store 传来的真实 currentNode）
  if (currentNode.value === key && status.value === 'running') {
    return 'bg-accent-blue/20 text-accent-blue border border-accent-blue/30 animate-pulse-glow'
  }
  return 'bg-terminal-hover text-data-muted border border-terminal-border'
}
</script>
