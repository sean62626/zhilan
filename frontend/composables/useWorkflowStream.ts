/**
 * 工作流 WebSocket 实时连接 composable
 *
 * 连接到 /ws/v1/workflow/{run_id} 接收节点完成、工作流完成/失败事件。
 * 自动重连（指数退避），组件卸载时自动断开。
 */

import type { WsEvent } from '~/types'

export function useWorkflowStream(runId: Ref<string | null>) {
  const connected = ref(false)
  const events = ref<WsEvent[]>([])
  const nodesCompleted = ref<string[]>([])

  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000
  let active = true

  // 是否正在使用直连模式（跳过 Nuxt 代理）
  const directMode = ref(false)

  function connect() {
    const id = runId.value
    if (!id || !active) return

    // SSR 守卫：服务端渲染时不建立 WebSocket 连接
    if (import.meta.server) return

    // 先断开旧连接，防止重复连接
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    // 构建 WebSocket URL
    // 优先走同域代理（Nginx / Docker），失败后直连后端（本地开发）
    let wsUrl: string
    if (directMode.value) {
      // 直连模式：用运行时配置中的 wsUrl
      const runtimeConfig = useRuntimeConfig()
      const backendWs = runtimeConfig.public.wsUrl || 'ws://localhost:8000'
      wsUrl = `${backendWs}/ws/v1/workflow/${id}`
    } else {
      // 如果当前页面是从 3000 端口（Nuxt 开发服务器）直连访问的，
      // 直接走直连模式，避免 WebSocket 请求打到 Nuxt 触发 Vue Router 警告
      const host = window.location.host
      if (host.endsWith(':3000')) {
        directMode.value = true
        const runtimeConfig = useRuntimeConfig()
        const backendWs = runtimeConfig.public.wsUrl || 'ws://localhost:8000'
        wsUrl = `${backendWs}/ws/v1/workflow/${id}`
      } else {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        wsUrl = `${protocol}//${host}/ws/v1/workflow/${id}`
      }
    }

    // 连接超时检测：2 秒内连不上就切换模式
    let connectTimer: ReturnType<typeof setTimeout> | null = null
    if (!directMode.value) {
      connectTimer = setTimeout(() => {
        directMode.value = true
        ws?.close()
      }, 2000)
    }

    try {
      ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        if (connectTimer) clearTimeout(connectTimer)
        connected.value = true
        reconnectDelay = 1000
      }

      ws.onmessage = (msg) => {
        try {
          const event: WsEvent = JSON.parse(msg.data)
          events.value = [...events.value.slice(-99), event]

          if (event.type === 'node_complete' && event.node && !nodesCompleted.value.includes(event.node)) {
            nodesCompleted.value = [...nodesCompleted.value, event.node]
          }
        } catch {
          // 忽略解析失败的消息
        }
      }

      ws.onclose = () => {
        if (connectTimer) clearTimeout(connectTimer)
        connected.value = false
        ws = null
        if (active && runId.value) {
          reconnectTimer = setTimeout(() => {
            reconnectDelay = Math.min(reconnectDelay * 2, 30000)
            connect()
          }, reconnectDelay)
        }
      }

      ws.onerror = () => {
        ws?.close()
      }
    } catch {
      if (connectTimer) clearTimeout(connectTimer)
      // WebSocket 创建失败，稍后重试
      if (active && runId.value) {
        reconnectTimer = setTimeout(() => {
          connect()
        }, 5000)
      }
    }
  }

  function disconnect() {
    active = false
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null // 阻止自动重连
      ws.close()
      ws = null
    }
    connected.value = false
  }

  // 监听 runId 变化
  watch(
    runId,
    (newId, oldId) => {
      if (oldId) disconnect()
      if (newId) {
        active = true
        connect()
      }
    },
    { immediate: true }
  )

  // 组件卸载时清理
  onBeforeUnmount(() => {
    disconnect()
  })

  return {
    connected: readonly(connected),
    events: readonly(events),
    nodesCompleted: readonly(nodesCompleted),
  }
}
