/**
 * API 调用 composable — 集中管理所有后端 API 请求
 *
 * 通过 Nuxt BFF 代理 (/api/v1/*) 调用 FastAPI 后端，
 * 避免跨域问题，统一错误处理。
 */

export function useApi() {
  const apiBase = '/api/v1'

  async function request<T = any>(path: string, options?: { method?: string; body?: any; params?: Record<string, any> }): Promise<T> {
    const method = (options?.method || 'GET') as any
    const body = options?.body
    const params = options?.params || {}

    const query = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .flatMap(([k, v]) => {
        // 支持数组参数：{ topics: ["a","b"] } → topics=a&topics=b
        if (Array.isArray(v)) {
          return v.map(item => `${encodeURIComponent(k)}=${encodeURIComponent(String(item))}`)
        }
        return `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`
      })
      .join('&')

    const url = query ? `${apiBase}${path}?${query}` : `${apiBase}${path}`

    const result = await $fetch<any>(url, {
      method,
      body: body ? JSON.stringify(body) : undefined,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      ignoreResponseError: true,
    })

    if (result && result.detail && !result.status) {
      throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail))
    }

    // BFF 代理错误响应（后端不可达时返回）
    if (result && result.healthy === false && result.error) {
      throw new Error(`后端服务不可用: ${result.error}`)
    }

    return result as T
  }

  // ========== 状态 ==========
  function getStatus() {
    return request<any>('/status')
  }

  // ========== 配置 ==========
  function getConfig() {
    return request<any>('/config')
  }

  function updateConfig(data: Record<string, any>) {
    return request<any>('/config', { method: 'PUT', body: data })
  }

  // ========== 采集 ==========
  function triggerCollection() {
    return request<any>('/collect', { method: 'POST' })
  }

  function getCollectionStatus() {
    return request<any>('/collect/status')
  }

  // ========== 工作流 ==========
  function startWorkflow(topics: string[] = []) {
    return request<any>('/workflow/run', {
      method: 'POST',
      params: topics.length > 0 ? { topics } : {},
    })
  }

  function getWorkflowStatus(runId: string) {
    return request<any>(`/workflow/status/${runId}`)
  }

  function stopWorkflow(runId: string) {
    return request<any>(`/workflow/${runId}/stop`, { method: 'POST' })
  }

  // ========== 简报 ==========
  function getBriefList() {
    return request<any>('/briefs')
  }

  function getBrief(date: string, runId?: string) {
    return request<any>(`/briefs/${date}`, {
      params: runId ? { run_id: runId } : {},
    })
  }

  function getBriefPdfUrl(date: string): string {
    return `${apiBase}/briefs/${date}/pdf`
  }

  // ========== 研报 ==========
  function getReportList() {
    return request<any>('/reports')
  }

  function getReport(id: string) {
    return request<any>(`/reports/${id}`)
  }

  // ========== 聚类 ==========
  function getClusters() {
    return request<any>('/clusters')
  }

  // ========== 主题 ==========
  function getTopics() {
    return request<any>('/topics')
  }

  function createTopic(data: { name: string; keywords: string[] }) {
    return request<any>('/topics', { method: 'POST', body: data })
  }

  function deleteTopic(id: string) {
    return request<any>(`/topics/${id}`, { method: 'DELETE' })
  }

  // ========== 任务 ==========
  function getJobs() {
    return request<any>('/jobs')
  }

  function getJobHistory(jobId: string, limit = 20) {
    return request<any>('/jobs/history', { params: { job_id: jobId, limit } })
  }

  function triggerJob(jobId: string) {
    return request<any>(`/jobs/${jobId}/trigger`, { method: 'POST' })
  }

  function enableJob(jobId: string) {
    return request<any>(`/jobs/${jobId}/enable`, { method: 'POST' })
  }

  function disableJob(jobId: string) {
    return request<any>(`/jobs/${jobId}/disable`, { method: 'POST' })
  }

  // ========== 爬取目标 ==========
  function getCrawlTargets() {
    return request<any>('/crawl-targets')
  }

  function createCrawlTarget(data: { name: string; url: string }) {
    return request<any>('/crawl-targets', { method: 'POST', body: data })
  }

  function deleteCrawlTarget(id: string) {
    return request<any>(`/crawl-targets/${id}`, { method: 'DELETE' })
  }

  function restoreCrawlTarget(id: string) {
    return request<any>(`/crawl-targets/${id}/restore`, { method: 'POST' })
  }

  // ========== Pipeline ==========
  function startPipeline(step?: string) {
    return request<any>('/pipeline/run', {
      method: 'POST',
      params: step ? { start_from: step } : {},
    })
  }

  function getPipelineStatus(runId: string) {
    return request<any>(`/pipeline/status/${runId}`)
  }

  return {
    getStatus,
    getConfig,
    updateConfig,
    triggerCollection,
    getCollectionStatus,
    startWorkflow,
    getWorkflowStatus,
    stopWorkflow,
    getBriefList,
    getBrief,
    getBriefPdfUrl,
    getReportList,
    getReport,
    getClusters,
    getTopics,
    createTopic,
    deleteTopic,
    getJobs,
    getJobHistory,
    triggerJob,
    enableJob,
    disableJob,
    getCrawlTargets,
    createCrawlTarget,
    deleteCrawlTarget,
    restoreCrawlTarget,
    startPipeline,
    getPipelineStatus,
  }
}
