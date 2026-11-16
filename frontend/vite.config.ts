import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // 浏览器访问同源/api，由Vite转发到FastAPI，开发时无需修改后端CORS。
  const proxy = { '/api': { target: env.BACKEND_URL || 'http://127.0.0.1:8002', changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, '') } };
  return {
    plugins: [react()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, strictPort: true, proxy },
    build: {
      chunkSizeWarningLimit: 1200,
      // 框架、界面组件、Markdown分别缓存，避免把整个工作台打成一个大文件。
      rollupOptions: { output: { manualChunks: {
        framework: ['react', 'react-dom', 'react-router-dom'],
        components: ['antd', '@ant-design/icons'],
        markdown: ['react-markdown', 'remark-gfm'],
      } } },
    },
  };
});
