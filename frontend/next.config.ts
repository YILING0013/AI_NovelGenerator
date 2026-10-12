import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");
const isProduction = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  // 独立验收可使用其他构建目录，不改写正在运行的本机服务产物。
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactCompiler: true,
  typescript: {
    // 生产构建不应读取可能由上次 dev 强制中断而残留的开发路由声明。
    tsconfigPath: isProduction ? "tsconfig.build.json" : "tsconfig.json",
  },
};

export default withNextIntl(nextConfig);
