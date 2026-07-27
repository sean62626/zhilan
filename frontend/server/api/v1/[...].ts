/**
 * API 代理 — 将所有 /api/v1/* 请求转发到 FastAPI 后端
 * Nuxt 文件系统路由：server/api/v1/[...].ts → /api/v1/**
 *
 * 完整转发 method、query params、request body 到后端
 *
 * 后端地址通过环境变量 BACKEND_URL 配置，默认 http://localhost:8000
 * Docker Compose 环境下自动使用 http://backend:8000（服务名）
 */
export default defineEventHandler(async (event) => {
  const url = getRequestURL(event)
  const config = useRuntimeConfig()
  const target = `${config.backendUrl}${url.pathname}${url.search}`;

  try {
    let body: any = undefined
    if (event.method !== 'GET' && event.method !== 'HEAD') {
      body = await readBody(event).catch(() => undefined)
    }

    const data = await $fetch(target, {
      method: event.method as any,
      body,
      headers: { 'Content-Type': 'application/json' },
      ignoreResponseError: true,
    });
    return data;
  } catch (error: any) {
    return {
      service: "zhilan-frontend-bff",
      healthy: false,
      error: error.message || "Unknown error",
    };
  }
});
