/* eslint-disable react-hooks/set-state-in-effect */
"use client";

import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export default function Navbar() {
  const t = useTranslations("nav");
  const router = useRouter();
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const currentLocale = pathname.startsWith("/en") ? "en" : "zh";

  const switchLocale = (locale: string) => {
    if (locale === currentLocale) return;
    const rest = pathname.replace(/^\/(zh|en)/, "") || "/";
    // 语言切换只替换 locale，保留 Writing 当前 workspace/view 等深链接状态。
    // locale 布局需要重新加载消息资源；完整导航也避免把服务端脚本当作客户端组件渲染。
    window.location.assign(`/${locale}${rest}${window.location.search}`);
  };

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  const goSettings = () => {
    router.push(`/${currentLocale}/settings`, { scroll: false });
  };

  const goHome = () => {
    router.push(`/${currentLocale}`);
  };

  return (
    <header className="sticky top-0 z-50 h-14 shrink-0 border-b border-border bg-surface/95 backdrop-blur-md">
      <div className="flex h-full w-full min-w-0 items-center justify-between gap-3 px-4 sm:px-6">
        <button
          onClick={goHome}
          className="flex min-h-11 min-w-0 items-center gap-2.5 rounded-md text-left text-base font-semibold text-foreground transition-colors hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          <svg className="size-5 shrink-0 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <path d="M4 4.5h6a3 3 0 0 1 3 3V21a4 4 0 0 0-4-2H4z" />
            <path d="M13 7.5a3 3 0 0 1 3-3h4V19h-3a4 4 0 0 0-4 2" />
          </svg>
          <span className="truncate">{t("title")}</span>
        </button>

        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          {/* Language Segmented Toggle */}
          <div className="flex items-center bg-surface-secondary rounded-lg p-0.5 border border-border">
            <button
              onClick={() => switchLocale("zh")}
              aria-pressed={currentLocale === "zh"}
              className={`min-h-9 rounded-md px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                currentLocale === "zh"
                  ? "bg-accent text-accent-foreground shadow-sm"
                  : "text-muted hover:text-foreground"
              }`}
            >
              中文
            </button>
            <button
              onClick={() => switchLocale("en")}
              aria-pressed={currentLocale === "en"}
              className={`min-h-9 rounded-md px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
                currentLocale === "en"
                  ? "bg-accent text-accent-foreground shadow-sm"
                  : "text-muted hover:text-foreground"
              }`}
            >
              EN
            </button>
          </div>

          {/* Theme Toggle */}
          {mounted && (
            <button
              onClick={toggleTheme}
              className="relative flex size-11 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
              title={t("theme")}
              aria-label={t("theme")}
            >
              {/* Sun Icon */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`absolute transition-all duration-300 ${
                  theme === "dark"
                    ? "opacity-100 rotate-0 scale-100"
                    : "opacity-0 -rotate-90 scale-0"
                }`}
              >
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2" />
                <path d="M12 20v2" />
                <path d="m4.93 4.93 1.41 1.41" />
                <path d="m17.66 17.66 1.41 1.41" />
                <path d="M2 12h2" />
                <path d="M20 12h2" />
                <path d="m6.34 17.66-1.41 1.41" />
                <path d="m19.07 4.93-1.41 1.41" />
              </svg>
              {/* Moon Icon */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`absolute transition-all duration-300 ${
                  theme === "dark"
                    ? "opacity-0 rotate-90 scale-0"
                    : "opacity-100 rotate-0 scale-100"
                }`}
              >
                <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
              </svg>
            </button>
          )}

          {/* Settings */}
          <button
            onClick={goSettings}
            className="flex size-11 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            title={t("settings")}
            aria-label={t("settings")}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
