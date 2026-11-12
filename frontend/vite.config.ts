import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
    allowedHosts: true,
  },
  build: {
    rollupOptions: {
      output: {
        // 按依赖域拆包：Element Plus 体积最大且极少变动，单独缓存；
        // 业务代码改动不会再让用户重下整个 vendor。
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("element-plus") || id.includes("@element-plus")) return "vendor-element";
          if (id.includes("/vue/") || id.includes("@vue/") || id.includes("vue-router") || id.includes("vue-demi")) return "vendor-vue";
          if (id.includes("axios")) return "vendor-axios";
          return "vendor";
        },
      },
    },
  },
});
