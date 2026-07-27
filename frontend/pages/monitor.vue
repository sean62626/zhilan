<script setup lang="ts">
/**
 * 实时监控页 — 工作流管道 + Agent 状态 + 定时任务 + 事件日志
 */
import type { WsEvent, JobInfo, JobRun } from '~/types'
import { useWorkflowStore } from '~/stores/workflow'

const workflowStore = useWorkflowStore()
const { getWorkflowStatus, getJobs, getJobHistory, triggerJob } = useApi()
const runIdInput = ref('')

// ========== 工作流 ==========

// 页面加载时：优先用 store 中的 runId（从 Dashboard 导航过来），
// 其次用 localStorage（页面刷新后恢复）
// HTTP 查询兜底 WebSocket 的历史事件（WebSocket 只能收到订阅之后的实时事件）
onMounted(async () => {
  const id = workflowStore.runId || localStorage.getItem('last_run_id')
  if (id) {
    runIdInput.value = id
    await checkRunStatus(id)
  }
})

async function checkRunStatus(id: string) {
  try {
    const res = await getWorkflowStatus(id)
    if (!workflowStore.runId) {
      workflowStore.runId = id
    }
    // 只在 HTTP 返回更多节点时才更新 nodesCompleted，
    // 防止覆盖 WebSocket 已实时推送的更新数据
    const httpNodes: string[] = res.nodes_completed || []
    if (httpNodes.length >= workflowStore.nodesCompleted.length) {
      workflowStore.nodesCompleted = httpNodes
    }
    workflowStore.stats = res.stats
    workflowStore.errors = res.errors || []
    if (res.status === 'completed') workflowStore.status = 'completed'
    else if (res.status === 'failed') workflowStore.status = 'failed'
    else if (res.status === 'cancelled') workflowStore.status = 'cancelled'
    else if (res.status === 'running') workflowStore.status = 'running'
    localStorage.setItem('last_run_id', id)
  } catch {
    if (!workflowStore.runId) {
      workflowStore.status = 'failed'
    }
  }
}

// WebSocket 连接
const { connected: wsConnected, events, nodesCompleted } = useWorkflowStream(
  computed(() => workflowStore.runId)
)

watch(events, (evts) => {
  const latest = evts[evts.length - 1]
  if (latest) workflowStore.handleWsEvent(latest)
})

// Agent 状态网格
const agents = [
  { key: 'collect', name: 'Collector', desc: '多源数据采集', icon: '📥' },
  { key: 'preprocess', name: 'Preprocessor', desc: '文本清洗标准化', icon: '🔧' },
  { key: 'dedup', name: 'Dedup', desc: '三层去重过滤', icon: '🔍' },
  { key: 'cluster', name: 'Cluster', desc: '语义聚类 + 标签', icon: '🔗' },
  { key: 'research', name: 'Researcher', desc: 'RAG 深度摘要', icon: '🧠' },
  { key: 'review', name: 'Reviewer', desc: '事实核查 + 幻觉检测', icon: '✅' },
  { key: 'compose', name: 'Composer', desc: '日报组装', icon: '📋' },
  { key: 'export', name: 'Exporter', desc: 'MD / PDF 导出', icon: '📦' },
]

function agentStatus(key: string): 'success' | 'warning' | 'info' | 'neutral' {
  if (workflowStore.nodesCompleted.includes(key)) {
    return workflowStore.status === 'cancelled' ? 'warning' : 'success'
  }
  if (workflowStore.currentNode === key && workflowStore.status === 'running') return 'info'
  if (workflowStore.status === 'failed') return 'neutral'
  return 'neutral'
}

// ========== 定时任务 ==========
const { data: jobsData, refresh: refreshJobs } = await useAsyncData(
  'monitor-jobs',
  () => getJobs()
)

const jobs = computed<JobInfo[]>(() => jobsData.value?.jobs || [])

const expandedJobId = ref<string | null>(null)
const jobHistoryMap = ref<Record<string, JobRun[]>>({})
const triggeringJob = ref<string | null>(null)

async function toggleJobHistory(jobId: string) {
  if (expandedJobId.value === jobId) {
    expandedJobId.value = null
    return
  }
  expandedJobId.value = jobId
  if (!jobHistoryMap.value[jobId]) {
    try {
      const res = await getJobHistory(jobId)
      jobHistoryMap.value[jobId] = res.history
    } catch { /* ignore */ }
  }
}

async function handleTriggerJob(jobId: string) {
  triggeringJob.value = jobId
  try {
    await triggerJob(jobId)
    // 稍等后刷新列表和历史
    setTimeout(async () => {
      await refreshJobs()
      if (expandedJobId.value === jobId) {
        const res = await getJobHistory(jobId)
        jobHistoryMap.value[jobId] = res.history
      }
    }, 1500)
  } catch { /* ignore */ }
  triggeringJob.value = null
}

function nextRunLabel(job: JobInfo): string {
  if (!job.next_run) return '—'
  const t = new Date(job.next_run)
  const now = Date.now()
  const diff = t.getTime() - now
  if (diff < 0) return '即将触发'
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins} 分钟后`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时后`
  return `${Math.floor(hours / 24)} 天后`
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between animate-fade-slide">
      <div>
        <h1 class="text-2xl font-display text-data-highlight mb-1">实时监控</h1>
        <p class="text-sm text-data-muted">
          工作流运行状态 · Agent 监控
        </p>
      </div>
      <div class="flex items-center gap-2">
        <StatusBadge
          :status="wsConnected ? 'success' : 'neutral'"
        >
          {{ wsConnected ? 'WS 已连接' : 'WS 离线' }}
        </StatusBadge>
      </div>
    </div>

    <!-- Run ID 输入 -->
    <section class="panel p-4 animate-fade-slide">
      <div class="flex items-center gap-3">
        <span class="text-xs text-data-muted shrink-0">Run ID:</span>
        <input
          v-model="runIdInput"
          placeholder="输入 workflow run_id..."
          class="flex-1 bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm text-data-text font-mono focus:outline-none focus:border-accent-blue/50 transition-colors"
        />
        <button
          class="px-4 py-1.5 rounded bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/80 transition-colors"
          @click="checkRunStatus(runIdInput)"
        >
          查询
        </button>
      </div>
    </section>

    <!-- 工作流管道 -->
    <section class="animate-fade-slide stagger-1 opacity-0">
      <WorkflowPipeline
        :nodes-completed="workflowStore.nodesCompleted"
        :status="workflowStore.status"
        :current-node="workflowStore.currentNode"
        :progress-message="workflowStore.progressMessage"
      />
    </section>

    <!-- Agent 状态网格 -->
    <section class="animate-fade-slide stagger-2 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4">Agent 状态</h2>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <div
          v-for="agent in agents"
          :key="agent.key"
          class="panel p-4 flex items-center gap-3"
        >
          <span class="text-xl">{{ agent.icon }}</span>
          <div class="min-w-0">
            <div class="flex items-center gap-2 mb-0.5">
              <span class="text-sm font-medium text-data-text">{{ agent.name }}</span>
              <StatusBadge
                :status="agentStatus(agent.key)"
                class="scale-75 origin-left"
              >
                {{ workflowStore.nodesCompleted.includes(agent.key) ? 'Done' : 'Idle' }}
              </StatusBadge>
            </div>
            <div class="text-[10px] text-data-muted truncate">{{ agent.desc }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 定时任务状态 -->
    <section class="animate-fade-slide stagger-3 opacity-0">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-sm font-semibold text-data-highlight">⏰ 定时任务</h2>
        <button
          class="text-xs text-data-muted hover:text-data-text transition-colors"
          @click="refreshJobs()"
        >
          🔄 刷新
        </button>
      </div>

      <div class="space-y-3">
        <div
          v-for="job in jobs"
          :key="job.job_id"
          :class="[
            'panel-hover p-4 rounded-lg border',
            job.enabled ? 'border-terminal-border' : 'border-terminal-border opacity-60',
          ]"
        >
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-3">
              <span class="text-sm font-medium text-data-text">{{ job.name }}</span>
              <StatusBadge :status="job.enabled ? 'success' : 'neutral'">
                {{ job.enabled ? '运行中' : '已禁用' }}
              </StatusBadge>
              <StatusBadge
                v-if="job.last_run"
                :status="job.last_run.success ? 'success' : 'error'"
                class="scale-90"
              >
                {{ job.last_run.success ? '成功' : '失败' }}
              </StatusBadge>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[10px] text-data-muted font-mono">
                {{ job.trigger === 'interval' ? `每 ${job.interval_hours}h` : job.cron_fields ? Object.values(job.cron_fields).join(':') : '—' }}
              </span>
              <button
                class="px-2 py-0.5 rounded text-[10px] font-medium border border-terminal-border text-data-muted hover:text-accent-blue hover:border-accent-blue/30 transition-all disabled:opacity-50"
                :disabled="triggeringJob === job.job_id"
                @click="handleTriggerJob(job.job_id)"
              >
                {{ triggeringJob === job.job_id ? '触发中...' : '▶ 立即触发' }}
              </button>
            </div>
          </div>

          <div class="flex items-center gap-4 text-[10px] text-data-muted">
            <span>
              下次运行:
              <span class="text-data-text font-mono">{{ nextRunLabel(job) }}</span>
            </span>
            <span v-if="job.next_run" class="text-data-muted/60">
              {{ new Date(job.next_run).toLocaleString('zh-CN') }}
            </span>
            <span v-if="job.last_run">
              上次耗时:
              <span class="text-data-text font-mono">{{ formatDuration(job.last_run.duration_ms) }}</span>
            </span>
          </div>

          <!-- 展开：执行历史 -->
          <button
            class="mt-2 text-[10px] text-accent-blue hover:text-accent-cyan transition-colors"
            @click="toggleJobHistory(job.job_id)"
          >
            {{ expandedJobId === job.job_id ? '收起历史 ▲' : '展开历史 ▼' }}
          </button>
          <div
            v-if="expandedJobId === job.job_id && jobHistoryMap[job.job_id]"
            class="mt-2 max-h-48 overflow-y-auto bg-terminal-bg rounded-lg p-3 font-mono text-[10px]"
          >
            <div
              v-for="run in (jobHistoryMap[job.job_id] || []).slice(0, 10)"
              :key="run.execution_id"
              class="flex items-center gap-3 py-1 border-b border-terminal-border/30 last:border-0"
            >
              <span
                class="w-1.5 h-1.5 rounded-full shrink-0"
                :class="run.success ? 'bg-accent-green' : run.success === false ? 'bg-accent-red' : 'bg-accent-amber'"
              />
              <span class="text-data-muted shrink-0 w-28">
                {{ new Date(run.started_at).toLocaleString('zh-CN') }}
              </span>
              <span class="text-data-muted shrink-0 w-16">
                {{ formatDuration(run.duration_ms) }}
              </span>
              <span
                class="truncate"
                :class="run.error ? 'text-accent-red' : 'text-data-text'"
              >
                {{ run.error || (run.success ? '成功' : '运行中') }}
              </span>
            </div>
            <div v-if="(jobHistoryMap[job.job_id] || []).length === 0" class="text-data-muted italic">
              暂无执行记录
            </div>
          </div>
        </div>

        <EmptyState
          v-if="jobs.length === 0"
          title="暂无定时任务"
          description="后端调度器未启动或未注册任务"
          icon="⏰"
        />
      </div>
    </section>
    <section class="panel p-5 animate-fade-slide stagger-3 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4">实时事件日志</h2>
      <div class="bg-terminal-bg rounded-lg p-4 max-h-80 overflow-y-auto font-mono text-xs space-y-1">
        <div
          v-for="(evt, i) in events.slice(-50)"
          :key="i"
          class="flex gap-3"
        >
          <span class="text-data-muted shrink-0">{{ evt.timestamp?.slice(11, 19) || '--:--:--' }}</span>
          <span
            :class="[
              'shrink-0 w-20',
              evt.type === 'node_complete' ? 'text-accent-green' :
              evt.type === 'workflow_complete' ? 'text-accent-blue' :
              evt.type === 'workflow_error' ? 'text-accent-red' :
              'text-data-muted',
            ]"
          >
            [{{ evt.type }}]
          </span>
          <span class="text-data-text truncate">
            {{ evt.message || evt.node || evt.error || evt.status || '-' }}
          </span>
        </div>
        <div v-if="events.length === 0" class="text-data-muted italic">
          等待事件...
        </div>
      </div>
    </section>
  </div>
</template>
