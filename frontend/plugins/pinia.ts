/**
 * Pinia 手动安装插件
 * 
 * 替代 @pinia/nuxt 模块，避免版本不兼容导致 "$pinia has only a getter" 错误。
 */
import { createPinia } from 'pinia'

export default defineNuxtPlugin((nuxtApp) => {
  const pinia = createPinia()
  nuxtApp.vueApp.use(pinia)
})
