import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  base: '/',
  // 翻译表在 gui/locales（Python 后端也用），开发服务器要允许读上一级目录
  server: { proxy: { '/api': 'http://127.0.0.1:8765' }, fs: { allow: ['..'] } },
  build: { chunkSizeWarningLimit: 2000 },
})
