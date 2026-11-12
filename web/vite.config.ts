import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 정적 파일로 빌드해 Jetson이나 시연 노트북에서 Node 없이 연다.
// base를 상대 경로로 둬야 dist를 폴더째 열거나 하위 경로에 올려도 동작한다.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    // 개발 중에는 /api 요청을 서버(FastAPI)로 넘긴다
    proxy: { "/api": "http://localhost:8000" },
  },
});
