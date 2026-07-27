// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: "2025-07-25",

  // 开发服务器绑定所有网络接口（Docker 兼容）
  devServer: {
    host: "0.0.0.0",
    port: 3000,
  },

  // 模块
  modules: ["@nuxtjs/tailwindcss"],

  // 全局 CSS
  css: ["~/assets/css/main.css"],

  // TypeScript
  typescript: {
    strict: true,
  },

  // 运行时配置
  runtimeConfig: {
    // BFF 代理目标（仅服务端可用）
    // Docker: http://backend:8000  |  本地开发: BACKEND_URL=http://localhost:8000
    backendUrl: process.env.BACKEND_URL || "http://backend:8000",
    public: {
      apiBase: "/api/v1",
      // WebSocket 后端直连地址（本地开发时 Nuxt 无法代理 WebSocket，浏览器直连后端）
      wsUrl: (process.env.BACKEND_URL || "http://localhost:8000").replace(/^http/, "ws"),
    },
  },


  // 应用配置
  app: {
    head: {
      title: "智览 — AI 研报平台",
      meta: [
        { charset: "utf-8" },
        { name: "viewport", content: "width=device-width, initial-scale=1" },
      ],
    },
  },
});
