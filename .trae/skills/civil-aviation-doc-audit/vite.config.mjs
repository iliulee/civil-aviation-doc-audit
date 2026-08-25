// vite.config.mjs — 资料员工作台构建配置
import { defineConfig } from 'vite';

export default defineConfig({
  // 相对路径，保证部署后 file:// 和子目录都能直接打开
  base: './',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
});