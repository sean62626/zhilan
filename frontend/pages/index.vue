<script setup lang="ts">
/**
 * Dashboard 工作台
 *
 * 数据密集型仪表盘：统计卡片 + 要闻 TOP5 + 工作流管道 + 最新研报
 */
import type { ServiceStatus, ClustersResponse, ReportSummary, BriefListItem, TopicConfig } from '~/types'
import { useWorkflowStore } from '~/stores/workflow'
import { useWorkflowStream } from '~/composables/useWorkflowStream'

const { getStatus, getBriefList, getReportList, getTopics, startWorkflow } = useApi()
const workflowStore = useWorkflowStore()

// 并行获取数据
const { data: health } = await useAsyncData<ServiceStatus>('dashboard-health', () =>
  getStatus().catch(() => ({
    service: 'zhilan',
    version: '?',
    environment: '?',
    healthy: false,
    dependencies: {},
  }))
)

const { data: briefList } = await useAsyncData<{ dates: BriefListItem[]; latest_date: string | null }>(
  'dashboard-briefs',
  () => getBriefList()
)

const { data: reportData } = await useAsyncData<{ reports: ReportSummary[] }>(
  'dashboard-reports',
  () => getReportList()
)

// 读取用户配置的监控主题
const { data: topicsData } = await useAsyncData(
  'dashboard-topics',
  () => getTopics()
)
const configuredTopics = computed<TopicConfig[]>(() => topicsData.value?.topics || [])

// API 可达但依赖离线 ≠ 后端异常
const apiReachable = computed(() => health.value?.service === 'zhilan-backend')
const depsConnected = computed(() => {
  if (!health.value?.dependencies) return 0
  return Object.values(health.value.dependencies).filter(d => d.status === 'connected').length
})

// 计算统计数字
const stats = computed(() => ({
  totalArticles: workflowStore.stats?.raw_articles || 0,
  totalClusters: workflowStore.stats?.topic_clusters || 0,
  totalReports: workflowStore.stats?.research_reports || 0,
  reviewPassed: workflowStore.stats?.review_passed ?? null,
}))

const latestDate = computed(() => briefList.value?.latest_date)
const reports = computed(() => reportData.value?.reports?.slice(0, 3) || [])
const hasWorkflowRun = computed(() => workflowStore.status !== 'idle')
const hasData = computed(() => briefList.value?.dates?.length || 0 > 0)

// 采集阶段有错误或无文章时显示警告
const collectionWarning = computed(() => {
  if (workflowStore.status !== 'completed' && workflowStore.status !== 'failed' && workflowStore.status !== 'cancelled') return null
  if (workflowStore.stats && workflowStore.stats.raw_articles > 0) return null
  if (workflowStore.collectionErrors.length > 0) {
    return workflowStore.collectionErrors.join('；')
  }
  return '所有采集源均未返回文章。请检查：NewsAPI Key 是否已配置、爬虫目标网站是否可达。'
})

async function triggerWorkflow() {
  // 直接从 API 获取最新话题配置，绕过 useAsyncData 缓存
  // 确保用户在 Settings 改完后立即生效
  const fresh = await getTopics()
  const freshTopics: TopicConfig[] = fresh?.topics || []
  // 只传关键词（扁平），主题名称通过后端 topics_detail 自动加载
  const topicQueries = freshTopics.flatMap(t => t.keywords)
  console.log('[DEBUG-triggerWorkflow] getTopics 返回:', fresh)
  console.log('[DEBUG-triggerWorkflow] freshTopics:', freshTopics)
  console.log('[DEBUG-triggerWorkflow] topicQueries:', topicQueries)
  await workflowStore.start(topicQueries)
}

// WebSocket 实时连接
const { connected: wsConnected, events: wsEvents } = useWorkflowStream(
  computed(() => workflowStore.runId)
)

watch(wsEvents, (evts) => {
  const latest = evts[evts.length - 1]
  if (latest) workflowStore.handleWsEvent(latest)
})
</script>

<template>
  <div class="space-y-6">
    <!-- 统计卡片 -->
    <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="stagger-1 opacity-0 animate-fade-slide">
        <StatCard
          label="今日文章数"
          :value="stats.totalArticles"
          unit="篇"
          icon="📥"
          accent="blue"
          :trend="stats.totalArticles > 0 ? 12 : undefined"
        />
      </div>
      <div class="stagger-2 opacity-0 animate-fade-slide">
        <StatCard
          label="主题簇数"
          :value="stats.totalClusters"
          unit="个"
          icon="🔗"
          accent="purple"
          :trend="stats.totalClusters > 0 ? 8 : undefined"
        />
      </div>
      <div class="stagger-3 opacity-0 animate-fade-slide">
        <StatCard
          label="研报生成"
          :value="stats.totalReports"
          unit="份"
          icon="📝"
          accent="cyan"
          :trend="stats.totalReports > 0 ? 5 : undefined"
        />
      </div>
      <div class="stagger-4 opacity-0 animate-fade-slide">
        <StatCard
          label="后端状态"
          :value="apiReachable ? '在线' : '异常'"
          icon="🟢"
          :accent="apiReachable ? 'green' : 'amber'"
        />
      </div>
    </section>

    <!-- 两列布局 -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- 左列：工作流 + 要闻 -->
      <div class="lg:col-span-2 space-y-6">
        <!-- 工作流控制面板 -->
        <section class="panel p-5 stagger-1 opacity-0 animate-fade-slide">
          <div class="flex items-center justify-between mb-4">
            <div>
              <h2 class="text-sm font-semibold text-data-highlight mb-1">工作流</h2>
              <p class="text-[10px] text-data-muted">
                LangGraph 8 节点全流程自动化
              </p>
            </div>
            <div class="flex items-center gap-3">
              <StatusBadge
                v-if="wsConnected"
                status="success"
              >
                WS 已连接
              </StatusBadge>
              <!-- 停止按钮（仅运行中可见） -->
              <button
                v-if="workflowStore.status === 'running'"
                class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 bg-accent-red/10 text-accent-red border border-accent-red/30 hover:bg-accent-red/20 active:scale-95"
                @click="workflowStore.stop()"
              >
                ⏹ 停止
              </button>
              <!-- 启动按钮（非运行状态可见） -->
              <button
                v-else
                class="px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 bg-accent-blue text-white hover:shadow-lg hover:shadow-accent-blue/20 active:scale-95"
                @click="triggerWorkflow"
              >
                ▶ 启动工作流
              </button>
            </div>
          </div>

          <template v-if="hasWorkflowRun">
            <WorkflowPipeline
              :nodes-completed="workflowStore.nodesCompleted"
              :status="workflowStore.status"
              :current-node="workflowStore.currentNode"
              :progress-message="workflowStore.progressMessage"
            />

            <!-- 采集警告：工作流完成但无文章时提示 -->
            <div
              v-if="collectionWarning"
              class="mt-4 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5"
            >
              <div class="flex items-start gap-2">
                <span class="text-amber-400 text-sm mt-0.5">⚠️</span>
                <div>
                  <p class="text-xs font-medium text-amber-300 mb-1">采集阶段未获取到文章</p>
                  <p class="text-[11px] text-amber-400/80 leading-relaxed">{{ collectionWarning }}</p>
                </div>
              </div>
            </div>
          </template>

          <EmptyState
            v-else
            title="尚未执行工作流"
            description="点击「启动工作流」开始全流程：采集 → 预处理 → 去重 → 聚类 → RAG 研报 → 审核 → 组装 → 导出"
            action-label="▶ 启动工作流"
            icon="🚀"
            @action="triggerWorkflow"
          />
        </section>

        <!-- 今日要闻 TOP5 -->
        <section class="panel p-5 stagger-2 opacity-0 animate-fade-slide">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-sm font-semibold text-data-highlight">🔴 今日要闻</h2>
            <NuxtLink
              v-if="latestDate"
              :to="`/briefs/${latestDate}`"
              class="text-xs text-accent-blue hover:text-accent-cyan transition-colors"
            >
              查看完整简报 →
            </NuxtLink>
          </div>
          <div v-if="latestDate" class="space-y-1">
            <NewsItem
              v-for="(item, i) in []
"
              :key="i"
              :item="item"
              :index="i + 1"
            />
          </div>
          <EmptyState
            v-else
            title="暂无要闻数据"
            description="启动工作流生成今日日报"
            icon="📰"
            action-label="启动工作流"
            @action="triggerWorkflow"
          />
        </section>
      </div>

      <!-- 右列：最新研报 + 系统状态 -->
      <div class="space-y-6">
        <!-- 最新研报 -->
        <section class="panel p-5 stagger-3 opacity-0 animate-fade-slide">
          <h2 class="text-sm font-semibold text-data-highlight mb-4">📝 最新研报</h2>
          <div v-if="reports.length > 0" class="space-y-3">
            <ReportCard
              v-for="r in reports"
              :key="r.report_id"
              :report="r"
            />
          </div>
          <EmptyState
            v-else
            title="暂无研报"
            description="启动工作流生成 RAG 深度研报"
            icon="📄"
          />
        </section>

        <!-- 系统依赖状态 -->
        <section class="panel p-5 stagger-4 opacity-0 animate-fade-slide">
          <h2 class="text-sm font-semibold text-data-highlight mb-4">⚡ 系统依赖</h2>
          <div v-if="health?.dependencies" class="space-y-2">
            <div class="flex items-center justify-between py-1.5">
              <span class="text-xs text-data-muted">基础设施</span>
              <StatusBadge
                :status="depsConnected === 3 ? 'success' : 'warning'"
              >
                {{ depsConnected }}/3 已连接
              </StatusBadge>
            </div>
            <div
              v-for="(dep, key) in health.dependencies"
              :key="key"
              class="flex items-center justify-between py-1.5"
            >
              <span class="text-xs text-data-muted capitalize">{{ key }}</span>
              <StatusBadge
                :status="dep.status === 'connected' ? 'success' : 'error'"
              >
                {{ dep.status === 'connected' ? '已连接' : '离线' }}
              </StatusBadge>
            </div>
            <p v-if="depsConnected === 0" class="text-[10px] text-data-muted mt-2">
              Docker 容器未启动，不影响页面浏览。执行采集/工作流需要先启动 docker-compose。
            </p>
          </div>
          <div v-else class="text-xs text-amber-400">
            API 无响应，请检查后端服务。
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
