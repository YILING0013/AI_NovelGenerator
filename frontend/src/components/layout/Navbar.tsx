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
    router.push(`/${locale}${rest}`);
  };

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  const goSettings = () => {
    router.push(`/${currentLocale}/settings`);
  };

  const goHome = () => {
    router.push(`/${currentLocale}`);
  };

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
        <button
          onClick={goHome}
          className="text-lg font-bold text-foreground hover:text-primary transition-colors cursor-pointer"
        >
          {t("title")}
        </button>

        <div className="flex items-center gap-2">
          {/* Language Segmented Toggle */}
          <div className="flex items-center bg-surface-secondary rounded-lg p-0.5 border border-border">
            <button
              onClick={() => switchLocale("zh")}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all duration-200 ${
                currentLocale === "zh"
                  ? "bg-accent text-white shadow-sm"
                  : "text-muted hover:text-foreground"
              }`}
            >
              中文
            </button>
            <button
              onClick={() => switchLocale("en")}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all duration-200 ${
                currentLocale === "en"
                  ? "bg-accent text-white shadow-sm"
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
              className="relative w-9 h-9 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-surface-secondary border border-transparent hover:border-border transition-all duration-200"
              title={t("theme")}
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
            className="w-9 h-9 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-surface-secondary border border-transparent hover:border-border transition-all duration-200"
            title={t("settings")}
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
