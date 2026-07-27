/**
 * BFF 层 — 后端健康检查代理
 * Nuxt Server Route 转发到 FastAPI
 */
export default defineEventHandler(async () => {
  const config = useRuntimeConfig();
  try {
    const data = await $fetch(`${config.backendUrl}/api/v1/status`);
    return data;
  } catch (error: any) {
    return {
      service: "zhilan-frontend-bff",
      healthy: false,
      error: error.message || "Unknown error",
    };
  }
});
