/**
 * 智览前端 — 类型定义
 */

// ========== WebSocket 事件 ==========

export interface WsEvent {
  type: 'node_started' | 'node_progress' | 'node_complete' | 'workflow_complete' | 'workflow_error' | 'workflow_cancelled' | 'connected' | 'heartbeat'
  node?: string
  run_id?: string
  status?: string
  error?: string
  message?: string
  state_summary?: WorkflowStateSummary
  collection_errors?: string[]
  timestamp?: string
}

// ========== 工作流 ==========

export interface WorkflowStatus {
  run_id: string
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'not_found'
  nodes_completed: string[]
  stats: WorkflowStateSummary
  errors: string[]
  dedup_stats: Record<string, unknown>
  collection_errors: string[]
}

export interface WorkflowStateSummary {
  raw_articles: number
  clean_articles: number
  unique_articles: number
  topic_clusters: number
  research_reports: number
  review_results: number
  review_passed: boolean
  retry_count: number
  export_paths: string[]
}

// ========== 系统状态 ==========

export interface ServiceStatus {
  service: string
  version: string
  environment: string
  healthy: boolean
  dependencies: Record<string, DependencyStatus>
  scheduler: SchedulerStatus
}

export interface DependencyStatus {
  status: 'connected' | 'disconnected'
  error?: string
  url?: string
  host?: string
  version?: string
}

export interface SchedulerStatus {
  status: 'running' | 'stopped' | 'error'
  jobs_count: number
  jobs: Record<string, string>
}

// ========== 聚类 ==========

export interface TopicCluster {
  cluster_id: string
  label: string
  keywords: string[]
  importance: number
  article_count: number
  articles: ClusterArticle[]
  representative_title?: string
}

export interface ClusterArticle {
  id: string
  title: string
  url?: string
  source_name?: string
  published_at?: string
}

export interface ClustersResponse {
  clusters: TopicCluster[]
  total_articles: number
  date_distribution: DateDistribution[]
}

export interface DateDistribution {
  date: string
  count: number
}

// ========== 简报 ==========

export interface BriefListItem {
  date: string
  run_id: string
  generated_at: string
  size_bytes: number
}

export interface DailyBrief {
  brief_id: string
  target_date: string
  top_news: TopNewsItem[]
  research_reports: BriefReport[]
  industry_briefs: IndustryBrief[]
  data_board: Record<string, number | string>
  tomorrow_focus: string[]
}

export interface TopNewsItem {
  title: string
  importance?: number
}

export interface BriefReport {
  title: string
  summary?: string
}

export interface IndustryBrief {
  industry: string
  summary: string
  article_count: number
}

// ========== 研报 ==========

export interface ReportSummary {
  report_id: string
  title: string
  cluster_id?: string
  cluster_label?: string
  importance?: number
  generated_at?: string
  background_preview?: string
  review_passed?: boolean
  review_suggestions?: string[]
  model_used?: string
}

export interface ReportFullResponse {
  report: ReportDetail | null
  review: ReviewResult | null
  cluster: TopicCluster | null
}

export interface ReportDetail {
  report_id: string
  title: string
  background?: string
  analysis?: string
  outlook?: string
  risk?: string
  model_used?: string
  generated_at?: string
  rag_info?: { docs_retrieved: number; docs_reranked: number }
  references: Reference[]
}

export interface ReviewResult {
  passed: boolean
  suggestions: string[]
  fact_errors?: string[]
  hallucination_issues?: string[]
}

export interface Reference {
  title?: string
  url?: string
}

// ========== 配置 ==========

export interface TopicConfig {
  id: string
  name: string
  keywords: string[]
  enabled?: boolean
}

export interface AppConfig {
  app_name: string
  app_version: string
  environment: string
  log_level: string
  llm_model: string
  llm_api_configured: boolean
  collection_interval_hours: number
  brief_generation_time: string
  es_host: string
  es_configured: boolean
  mysql_configured: boolean
  redis_configured: boolean
  newsapi_configured: boolean
  crawler_enabled: boolean
}

// ========== 定时任务 ==========

export interface JobInfo {
  job_id: string
  name: string
  enabled: boolean
  trigger: 'interval' | 'cron'
  interval_hours?: number
  cron_fields?: Record<string, string>
  next_run: string | null
  last_run: JobRun | null
}

export interface JobRun {
  execution_id: string
  started_at: string
  duration_ms: number
  success: boolean | null
  error?: string
}

// ========== 爬取目标 ==========

export interface CrawlTarget {
  id: string
  name: string
  url: string
  source: 'system' | 'user'
  enabled: boolean
  deleted_system?: boolean
  created_at: string
}
