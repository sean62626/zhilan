/**
 * 工作流状态管理 — Pinia Store
 *
 * 管理工作流运行状态：启动、轮询、WebSocket 事件处理
 */
import { defineStore } from 'pinia'
import type { WsEvent, WorkflowStatus } from '~/types'

export const useWorkflowStore = defineStore('workflow', () => {
  const runId = ref<string | null>(null)
  const status = ref<'idle' | 'running' | 'completed' | 'failed' | 'cancelled'>('idle')
  const nodesCompleted = ref<string[]>([])
  /** 当前正在执行的节点（由 node_started 事件设置），null = 无节点在运行 */
  const currentNode = ref<string | null>(null)
  const stats = ref<WorkflowStatus['stats'] | null>(null)
  const errors = ref<string[]>([])
  const collectionErrors = ref<string[]>([])
  const lastEvent = ref<WsEvent | null>(null)
  /** 当前节点的详细进度消息（由 node_progress 事件设置），null = 无详情 */
  const progressMessage = ref<string | null>(null)

  // 所有 8 个工作流节点的顺序
  const ALL_NODES = [
    'collect',
    'preprocess',
    'dedup',
    'cluster',
    'research',
    'review',
    'compose',
    'export',
  ]

  const progress = computed(() => {
    if (status.value === 'completed') return 100
    if (status.value === 'cancelled') {
      const done = nodesCompleted.value.filter((n) => ALL_NODES.includes(n)).length
      return Math.round((done / ALL_NODES.length) * 100)
    }
    if (status.value === 'idle') return 0
    const done = nodesCompleted.value.filter((n) => ALL_NODES.includes(n)).length
    return Math.round((done / ALL_NODES.length) * 100)
  })

  async function start(topics: string[] = []) {
    const { startWorkflow, getWorkflowStatus } = useApi()

    // 清理上一次的轮询定时器
    _clearPoll()

    status.value = 'running'
    currentNode.value = 'collect'  // 第一个节点即将开始执行
    nodesCompleted.value = []
    stats.value = null
    errors.value = []
    collectionErrors.value = []

    try {
      const res = await startWorkflow(topics)
      runId.value = res.run_id
      localStorage.setItem('last_run_id', res.run_id)
      // 开始轮询（WebSocket 兜底）
      _startPoll(res.run_id)
    } catch (e: any) {
      status.value = 'failed'
      errors.value = [e.message || '启动工作流失败']
    }
  }

  function handleWsEvent(event: WsEvent) {
    lastEvent.value = event
    switch (event.type) {
      case 'node_started':
        // 实时更新当前正在执行的节点 — 这是解决 UI 不同步的关键
        if (event.node) {
          currentNode.value = event.node
        }
        // 新节点开始，清除上一条进度消息
        progressMessage.value = null
        break
      case 'node_progress':
        // 详细进度通知 — 显示节点内部子步骤
        if (event.message) {
          console.log('[workflow] 收到进度:', event.message)
          progressMessage.value = event.message
        }
        break
      case 'node_complete':
        if (event.node && !nodesCompleted.value.includes(event.node)) {
          nodesCompleted.value = [...nodesCompleted.value, event.node]
        }
        // 节点完成，清除该节点的进度消息
        progressMessage.value = null
        // 将 currentNode 推进到下一个预期的节点
        {
          const idx = event.node ? ALL_NODES.indexOf(event.node) : -1
          currentNode.value = (idx >= 0 && idx < ALL_NODES.length - 1) ? ALL_NODES[idx + 1] : null
        }
        break
      case 'workflow_complete':
        status.value = 'completed'
        currentNode.value = null
        progressMessage.value = null
        _clearPoll()
        if (event.state_summary) {
          stats.value = event.state_summary as any
        }
        if (event.collection_errors?.length > 0) {
          collectionErrors.value = event.collection_errors
        }
        break
      case 'workflow_cancelled':
        status.value = 'cancelled'
        currentNode.value = null
        progressMessage.value = null
        _clearPoll()
        if (event.state_summary) {
          stats.value = event.state_summary as any
        }
        break
      case 'workflow_error':
        status.value = 'failed'
        currentNode.value = null
        progressMessage.value = null
        _clearPoll()
        if (event.error) {
          errors.value = [...errors.value, event.error]
        }
        break
      // connected / heartbeat — 仅更新连接状态，不改变工作流状态
      case 'connected':
      case 'heartbeat':
        break
    }
  }

  // ========== HTTP 轮询（WebSocket 的兜底） ==========

  let _pollTimer: ReturnType<typeof setInterval> | null = null

  function _clearPoll() {
    if (_pollTimer !== null) {
      clearInterval(_pollTimer)
      _pollTimer = null
    }
  }

  function _startPoll(id: string) {
    const { getWorkflowStatus } = useApi()
    const maxPolls = 120
    let polls = 0

    _pollTimer = setInterval(async () => {
      polls++
      // 已完成/失败/取消 → 停止轮询
      const terminalStatuses = ['completed', 'failed', 'cancelled']
      if (polls > maxPolls || terminalStatuses.includes(status.value)) {
        _clearPoll()
        return
      }

      try {
        const res = await getWorkflowStatus(id)
        // 只在 HTTP 返回更多节点时才更新，防止覆盖 WebSocket 实时推送
        const httpNodes: string[] = res.nodes_completed || []
        if (httpNodes.length >= nodesCompleted.value.length) {
          nodesCompleted.value = httpNodes
        }
        // 从 HTTP 响应推断当前节点（WebSocket 不可用时的兜底）
        // 只在 WebSocket 未提供更新值时覆盖，避免覆盖更实时的 node_started 事件
        if (res.status === 'running' && httpNodes.length > 0) {
          const lastDone = httpNodes[httpNodes.length - 1]
          const idx = ALL_NODES.indexOf(lastDone)
          const inferred = (idx >= 0 && idx < ALL_NODES.length - 1) ? ALL_NODES[idx + 1] : null
          if (currentNode.value === null || (inferred && ALL_NODES.indexOf(inferred) > ALL_NODES.indexOf(currentNode.value))) {
            currentNode.value = inferred
          }
        }
        stats.value = res.stats
        errors.value = res.errors || []
        if (res.collection_errors?.length > 0) {
          collectionErrors.value = res.collection_errors
        }

        if (res.status === 'completed') {
          status.value = 'completed'
          _clearPoll()
        } else if (res.status === 'failed') {
          status.value = 'failed'
          _clearPoll()
        } else if (res.status === 'cancelled') {
          status.value = 'cancelled'
          _clearPoll()
        }
      } catch {
        // 轮询失败不中断
      }
    }, 5000)
  }

  function reset() {
    _clearPoll()
    runId.value = null
    status.value = 'idle'
    currentNode.value = null
    progressMessage.value = null
    nodesCompleted.value = []
    stats.value = null
    errors.value = []
    collectionErrors.value = []
    lastEvent.value = null
  }

  async function stop() {
    const { stopWorkflow } = useApi()
    if (!runId.value) return

    try {
      await stopWorkflow(runId.value)
      // 不立即改状态 — 等待 WebSocket workflow_cancelled 事件
      // 如果 3 秒内没有收到事件，手动设为 cancelled
      const currentRunId = runId.value
      setTimeout(() => {
        if (runId.value === currentRunId && status.value === 'running') {
          _clearPoll()
          status.value = 'cancelled'
          errors.value = [...errors.value, '用户手动停止']
        }
      }, 3000)
    } catch (e: any) {
      errors.value = [...errors.value, e.data?.detail || e.message || '停止失败']
    }
  }

  return {
    runId,
    status,
    nodesCompleted,
    stats,
    errors,
    collectionErrors,
    lastEvent,
    ALL_NODES,
    currentNode,
    progressMessage,
    progress,
    start,
    handleWsEvent,
    reset,
    stop,
  }
})
