"use client";

import { I18nProvider } from "@heroui/react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function Providers({ children, locale }: { children: React.ReactNode; locale: string }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <I18nProvider locale={locale}>
        {children}
      </I18nProvider>
    </NextThemesProvider>
  );
}
