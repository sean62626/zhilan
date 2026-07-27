<script setup lang="ts">
/**
 * 系统配置页 — 主题管理 + 数据源 + 采集设置 + 任务控制
 */
import type { TopicConfig, AppConfig, JobInfo, CrawlTarget } from '~/types'

const { getTopics, createTopic, deleteTopic, getConfig, updateConfig, getJobs, triggerJob, enableJob, disableJob, getCrawlTargets, createCrawlTarget, deleteCrawlTarget, restoreCrawlTarget } = useApi()

// ========== 主题管理 ==========
const { data: topicsData, refresh: refreshTopics } = await useAsyncData(
  'settings-topics',
  () => getTopics()
)

const topics = computed<TopicConfig[]>(() => topicsData.value?.topics || [])

const newTopicName = ref('')
const newTopicKeywords = ref('')
const topicSaving = ref(false)
const topicError = ref('')

async function addTopic() {
  if (!newTopicName.value.trim()) {
    topicError.value = '主题名称不能为空'
    return
  }
  topicSaving.value = true
  topicError.value = ''
  try {
    await createTopic({
      name: newTopicName.value.trim(),
      keywords: newTopicKeywords.value.split(',').map(k => k.trim()).filter(Boolean),
    })
    newTopicName.value = ''
    newTopicKeywords.value = ''
    await refreshTopics()
  } catch (e: any) {
    topicError.value = e.data?.detail || e.message || '创建失败'
  } finally {
    topicSaving.value = false
  }
}

async function removeTopic(id: string) {
  try {
    await deleteTopic(id)
    await refreshTopics()
  } catch (e: any) {
    topicError.value = e.data?.detail || e.message || '删除失败'
  }
}

// ========== 爬取目标管理 ==========
const { data: crawlTargetsData, refresh: refreshCrawlTargets } = await useAsyncData(
  'settings-crawl-targets',
  () => getCrawlTargets()
)

const crawlTargets = computed<CrawlTarget[]>(() => crawlTargetsData.value?.targets || [])
const deletedTargets = computed<CrawlTarget[]>(() => crawlTargetsData.value?.deleted_targets || [])

const newTargetName = ref('')
const newTargetUrl = ref('')
const targetSaving = ref(false)
const targetError = ref('')

async function addCrawlTarget() {
  if (!newTargetName.value.trim()) {
    targetError.value = '网站名称不能为空'
    return
  }
  if (!newTargetUrl.value.trim()) {
    targetError.value = 'URL 不能为空'
    return
  }
  targetSaving.value = true
  targetError.value = ''
  try {
    await createCrawlTarget({
      name: newTargetName.value.trim(),
      url: newTargetUrl.value.trim(),
    })
    newTargetName.value = ''
    newTargetUrl.value = ''
    await refreshCrawlTargets()
  } catch (e: any) {
    targetError.value = e.data?.detail || e.message || '添加失败'
  } finally {
    targetSaving.value = false
  }
}

async function removeCrawlTarget(id: string) {
  try {
    await deleteCrawlTarget(id)
    await refreshCrawlTargets()
  } catch (e: any) {
    targetError.value = e.data?.detail || e.message || '删除失败'
  }
}

async function restoreTarget(id: string) {
  try {
    await restoreCrawlTarget(id)
    await refreshCrawlTargets()
  } catch (e: any) {
    targetError.value = e.data?.detail || e.message || '恢复失败'
  }
}

// ========== 系统配置 ==========
const { data: configData, refresh: refreshConfig } = await useAsyncData(
  'settings-config',
  () => getConfig()
)

const config = computed<AppConfig | null>(() => configData.value?.config || null)

const configForm = reactive({
  collection_interval_hours: 2,
  brief_generation_time: '08:00',
  log_level: 'INFO',
})
const configSaving = ref(false)
const configSaved = ref(false)

watchEffect(() => {
  if (config.value) {
    configForm.collection_interval_hours = config.value.collection_interval_hours
    configForm.brief_generation_time = config.value.brief_generation_time
    configForm.log_level = config.value.log_level
  }
})

async function saveConfig() {
  configSaving.value = true
  configSaved.value = false
  try {
    await updateConfig({
      collection_interval_hours: configForm.collection_interval_hours,
      brief_generation_time: configForm.brief_generation_time,
      log_level: configForm.log_level,
    })
    configSaved.value = true
    setTimeout(() => { configSaved.value = false }, 3000)
    await refreshConfig()
  } catch (e: any) {
    // ignore save errors
  } finally {
    configSaving.value = false
  }
}

// ========== 定时任务控制 ==========

const { data: jobsData, refresh: refreshJobs } = await useAsyncData(
  'settings-jobs',
  () => getJobs()
)

const jobs = computed<JobInfo[]>(() => jobsData.value?.jobs || [])
const jobToggling = ref<string | null>(null)
const jobTriggering = ref<string | null>(null)

function findJob(jobId: string): JobInfo | undefined {
  return jobs.value.find(j => j.job_id === jobId)
}

async function toggleJob(jobId: string) {
  const job = findJob(jobId)
  if (!job) return
  jobToggling.value = jobId
  try {
    if (job.enabled) {
      await disableJob(jobId)
    } else {
      await enableJob(jobId)
    }
    await refreshJobs()
  } catch { /* ignore */ }
  jobToggling.value = null
}

async function handleTriggerJob(jobId: string) {
  jobTriggering.value = jobId
  try {
    await triggerJob(jobId)
    setTimeout(async () => { await refreshJobs() }, 1500)
  } catch { /* ignore */ }
  jobTriggering.value = null
}

// ========== 数据源状态 ==========
const sourceConfigs = [
  { key: 'newsapi', label: 'NewsAPI', desc: '全球新闻聚合', configured: computed(() => config.value?.newsapi_configured) },
  { key: 'crawler', label: '自定义爬虫', desc: '新浪财经 · 东方财富', configured: computed(() => config.value?.crawler_enabled) },
]
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- 标题栏 -->
    <div class="animate-fade-slide">
      <h1 class="text-2xl font-display text-data-highlight mb-1">系统配置</h1>
      <p class="text-sm text-data-muted">监控主题 · 数据源 · 采集设置</p>
    </div>

    <!-- 监控主题管理 -->
    <section class="panel p-6 animate-fade-slide stagger-1 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4 flex items-center gap-2">
        <span class="w-1 h-5 rounded-full bg-accent-purple" />
        🔍 监控主题
      </h2>

      <!-- 现有主题列表 -->
      <div v-if="topics.length > 0" class="space-y-2 mb-4">
        <div
          v-for="t in topics"
          :key="t.id"
          class="flex items-center justify-between p-3 rounded-lg bg-terminal-hover/50 border border-terminal-border"
        >
          <div>
            <div class="text-sm font-medium text-data-text">{{ t.name }}</div>
            <div class="flex flex-wrap gap-1 mt-1">
              <span
                v-for="kw in t.keywords"
                :key="kw"
                class="px-1.5 py-0.5 rounded text-[10px] bg-terminal-bg text-data-muted"
              >
                {{ kw }}
              </span>
            </div>
          </div>
          <button
            class="text-xs text-accent-red hover:text-red-400 transition-colors px-2 py-1"
            @click="removeTopic(t.id)"
          >
            删除
          </button>
        </div>
      </div>
      <EmptyState
        v-else
        title="暂无监控主题"
        description="创建主题关键词以开始监控"
        icon="🔍"
      />

      <!-- 新增主题表单 -->
      <div class="mt-4 p-4 rounded-lg bg-terminal-bg/50 border border-terminal-border">
        <div class="text-xs font-medium text-data-text mb-3">新增主题</div>
        <div class="flex items-end gap-3">
          <div class="flex-1">
            <label class="text-[10px] text-data-muted block mb-1">主题名称</label>
            <input
              v-model="newTopicName"
              placeholder="例如：AI 大模型"
              class="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm text-data-text focus:outline-none focus:border-accent-blue/50 transition-colors"
              @keyup.enter="addTopic"
            />
          </div>
          <div class="flex-[2]">
            <label class="text-[10px] text-data-muted block mb-1">关键词（逗号分隔）</label>
            <input
              v-model="newTopicKeywords"
              placeholder="AI, 大模型, LLM, AGI"
              class="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm text-data-text focus:outline-none focus:border-accent-blue/50 transition-colors"
              @keyup.enter="addTopic"
            />
          </div>
          <button
            class="px-4 py-1.5 rounded bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/80 transition-colors disabled:opacity-50 shrink-0"
            :disabled="topicSaving"
            @click="addTopic"
          >
            {{ topicSaving ? '...' : '+ 添加' }}
          </button>
        </div>
        <p v-if="topicError" class="text-xs text-accent-red mt-2">{{ topicError }}</p>
      </div>
    </section>

    <!-- 数据源配置 -->
    <section class="panel p-6 animate-fade-slide stagger-2 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4 flex items-center gap-2">
        <span class="w-1 h-5 rounded-full bg-accent-green" />
        📡 数据源
      </h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div
          v-for="src in sourceConfigs"
          :key="src.key"
          class="p-4 rounded-lg bg-terminal-hover/50 border"
          :class="src.configured.value ? 'border-accent-green/20' : 'border-terminal-border'"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm font-medium text-data-text">{{ src.label }}</span>
            <StatusBadge
              :status="src.configured.value ? 'success' : 'neutral'"
            >
              {{ src.configured.value ? '已配置' : '未配置' }}
            </StatusBadge>
          </div>
          <p class="text-[10px] text-data-muted">{{ src.desc }}</p>
        </div>
      </div>
    </section>

    <!-- 自定义爬取网站 -->
    <section class="panel p-6 animate-fade-slide stagger-2-5 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4 flex items-center gap-2">
        <span class="w-1 h-5 rounded-full bg-accent-amber" />
        🌐 自定义爬取网站
      </h2>
      <p class="text-[10px] text-data-muted mb-4">
        爬虫将访问这些网站的列表页，自动提取当日文章。所有站点均可删除。
      </p>

      <!-- 目标列表 -->
      <div v-if="crawlTargets.length > 0" class="space-y-2 mb-4">
        <div
          v-for="t in crawlTargets"
          :key="t.id"
          class="flex items-center justify-between p-3 rounded-lg bg-terminal-hover/50 border border-terminal-border"
        >
          <div class="flex items-center gap-3 min-w-0">
            <span class="text-sm text-data-text truncate">{{ t.name }}</span>
            <span class="text-[10px] text-data-muted font-mono truncate hidden sm:inline">{{ t.url }}</span>
            <span
              class="px-1.5 py-0.5 rounded text-[10px] shrink-0"
              :class="t.source === 'system' ? 'bg-accent-blue/10 text-accent-blue' : 'bg-accent-purple/10 text-accent-purple'"
            >
              {{ t.source === 'system' ? '系统预设' : '自定义' }}
            </span>
          </div>
          <button
            class="text-xs text-accent-red hover:text-red-400 transition-colors px-2 py-1 shrink-0"
            @click="removeCrawlTarget(t.id)"
          >
            删除
          </button>
        </div>
      </div>
      <EmptyState
        v-else
        title="暂无爬取目标"
        description="添加网站 URL 开始自定义爬取"
        icon="🌐"
      />

      <!-- 已删除的系统预设（可恢复） -->
      <div v-if="deletedTargets.length > 0" class="mt-4 space-y-2">
        <div class="text-xs font-medium text-data-muted mb-2">🗑️ 已删除的站点</div>
        <div
          v-for="t in deletedTargets"
          :key="t.id"
          class="flex items-center justify-between p-3 rounded-lg bg-terminal-bg/30 border border-accent-red/10 opacity-60 hover:opacity-80 transition-opacity"
        >
          <div class="flex items-center gap-3 min-w-0">
            <span class="text-sm text-data-muted truncate">{{ t.name }}</span>
            <span class="text-[10px] text-data-muted font-mono truncate hidden sm:inline">{{ t.url }}</span>
            <span class="px-1.5 py-0.5 rounded text-[10px] bg-accent-red/10 text-accent-red shrink-0">
              已删除
            </span>
          </div>
          <button
            class="text-xs text-accent-green hover:text-green-400 transition-colors px-2 py-1 shrink-0"
            @click="restoreTarget(t.id)"
          >
            恢复
          </button>
        </div>
      </div>

      <!-- 新增表单 -->
      <div class="mt-4 p-4 rounded-lg bg-terminal-bg/50 border border-terminal-border">
        <div class="text-xs font-medium text-data-text mb-3">新增爬取网站</div>
        <div class="flex items-end gap-3">
          <div class="flex-1">
            <label class="text-[10px] text-data-muted block mb-1">网站名称</label>
            <input
              v-model="newTargetName"
              placeholder="例如：华尔街见闻"
              class="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm text-data-text focus:outline-none focus:border-accent-amber/50 transition-colors"
              @keyup.enter="addCrawlTarget"
            />
          </div>
          <div class="flex-[2]">
            <label class="text-[10px] text-data-muted block mb-1">网站 URL</label>
            <input
              v-model="newTargetUrl"
              placeholder="https://example.com/news"
              class="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm text-data-text focus:outline-none focus:border-accent-amber/50 transition-colors"
              @keyup.enter="addCrawlTarget"
            />
          </div>
          <button
            class="px-4 py-1.5 rounded bg-accent-amber text-white text-sm font-medium hover:bg-accent-amber/80 transition-colors disabled:opacity-50 shrink-0"
            :disabled="targetSaving"
            @click="addCrawlTarget"
          >
            {{ targetSaving ? '...' : '+ 添加' }}
          </button>
        </div>
        <p v-if="targetError" class="text-xs text-accent-red mt-2">{{ targetError }}</p>
      </div>
    </section>

    <!-- 采集设置 -->
    <section class="panel p-6 animate-fade-slide stagger-3 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4 flex items-center gap-2">
        <span class="w-1 h-5 rounded-full bg-accent-cyan" />
        ⏱️ 采集设置
      </h2>
      <div class="space-y-4" v-if="config">
        <!-- 采集间隔 -->
        <div>
          <label class="text-xs text-data-muted block mb-1">
            采集间隔: {{ configForm.collection_interval_hours }} 小时
          </label>
          <input
            v-model.number="configForm.collection_interval_hours"
            type="range"
            min="1"
            max="24"
            class="w-full h-1.5 rounded-full appearance-none bg-terminal-border accent-accent-blue cursor-pointer"
          />
          <div class="flex justify-between text-[10px] text-data-muted mt-1">
            <span>1h</span>
            <span>12h</span>
            <span>24h</span>
          </div>
        </div>

        <!-- 简报生成时间 -->
        <div>
          <label class="text-xs text-data-muted block mb-1">日报生成时间</label>
          <input
            v-model="configForm.brief_generation_time"
            type="time"
            class="bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 text-sm text-data-text font-mono focus:outline-none focus:border-accent-blue/50 transition-colors w-40"
          />
        </div>

        <!-- 日志级别 -->
        <div>
          <label class="text-xs text-data-muted block mb-1">日志级别</label>
          <div class="flex gap-2">
            <button
              v-for="level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']"
              :key="level"
              class="px-3 py-1 rounded text-xs font-medium transition-all border"
              :class="[
                configForm.log_level === level
                  ? 'bg-accent-blue/10 text-accent-blue border-accent-blue/30'
                  : 'bg-terminal-bg text-data-muted border-terminal-border hover:border-accent-blue/20',
              ]"
              @click="configForm.log_level = level"
            >
              {{ level }}
            </button>
          </div>
        </div>

        <!-- 保存按钮 -->
        <div class="flex items-center gap-3 pt-2">
          <button
            class="px-5 py-2 rounded-lg bg-accent-blue text-white text-sm font-medium hover:bg-accent-blue/80 transition-all disabled:opacity-50"
            :disabled="configSaving"
            @click="saveConfig"
          >
            {{ configSaving ? '保存中...' : '💾 保存配置' }}
          </button>
          <span v-if="configSaved" class="text-xs text-accent-green">✓ 已保存</span>
        </div>

        <!-- 任务启停控制 -->
        <div class="mt-6 pt-4 border-t border-terminal-border">
          <div class="text-xs font-medium text-data-text mb-3">📋 任务控制</div>
          <div class="space-y-3">
            <div
              v-for="job in jobs"
              :key="job.job_id"
              class="flex items-center justify-between p-3 rounded-lg bg-terminal-hover/30 border border-terminal-border"
            >
              <div class="flex items-center gap-3">
                <span class="text-sm text-data-text">{{ job.name }}</span>
                <StatusBadge
                  :status="job.enabled ? 'success' : 'neutral'"
                  class="scale-90"
                >
                  {{ job.enabled ? '启用' : '禁用' }}
                </StatusBadge>
                <span class="text-[10px] text-data-muted font-mono">
                  {{ job.trigger === 'interval' ? `每${job.interval_hours}h` : '定时' }}
                </span>
                <span
                  v-if="job.last_run"
                  class="text-[10px]"
                  :class="job.last_run.success ? 'text-accent-green' : 'text-accent-red'"
                >
                  {{ job.last_run.success ? '✓' : '✗' }}
                  {{ new Date(job.last_run.started_at).toLocaleString('zh-CN') }}
                </span>
              </div>
              <div class="flex items-center gap-2">
                <button
                  class="px-2 py-1 rounded text-[10px] font-medium border border-terminal-border text-data-muted hover:text-accent-blue hover:border-accent-blue/30 transition-all disabled:opacity-50"
                  :disabled="jobTriggering === job.job_id"
                  @click="handleTriggerJob(job.job_id)"
                >
                  {{ jobTriggering === job.job_id ? '...' : '▶ 触发' }}
                </button>
                <button
                  class="px-3 py-1 rounded text-[10px] font-medium border transition-all disabled:opacity-50"
                  :class="[
                    job.enabled
                      ? 'border-accent-red/30 text-accent-red hover:bg-accent-red/10'
                      : 'border-accent-green/30 text-accent-green hover:bg-accent-green/10',
                  ]"
                  :disabled="jobToggling === job.job_id"
                  @click="toggleJob(job.job_id)"
                >
                  {{ jobToggling === job.job_id ? '...' : (job.enabled ? '禁用' : '启用') }}
                </button>
              </div>
            </div>

            <EmptyState
              v-if="jobs.length === 0"
              title="暂无定时任务"
              description="后端调度器未启动"
              icon="⏰"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- 系统状态摘要 -->
    <section v-if="config" class="panel p-6 animate-fade-slide stagger-4 opacity-0">
      <h2 class="text-sm font-semibold text-data-highlight mb-4">📊 系统摘要</h2>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <div>
          <span class="text-data-muted">环境</span>
          <div class="text-data-text font-mono mt-0.5">{{ config.environment }}</div>
        </div>
        <div>
          <span class="text-data-muted">LLM 模型</span>
          <div class="text-data-text font-mono mt-0.5">{{ config.llm_model }}</div>
        </div>
        <div>
          <span class="text-data-muted">LLM API</span>
          <div class="text-data-text font-mono mt-0.5">
            <StatusBadge :status="config.llm_api_configured ? 'success' : 'warning'" class="scale-90">
              {{ config.llm_api_configured ? 'Configured' : 'Not set' }}
            </StatusBadge>
          </div>
        </div>
        <div>
          <span class="text-data-muted">OpenSearch 连接</span>
          <div class="text-data-text font-mono mt-0.5">{{ config.es_host }}</div>
        </div>
      </div>
    </section>
  </div>
</template>
