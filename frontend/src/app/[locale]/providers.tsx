"use client";

import { I18nProvider } from "@heroui/react";
import { ThemeProvider as NextThemesProvider } from "next-themes";
import { ThemeCustomizationProvider } from "@/components/ThemeCustomizationProvider";

export function Providers({ children, locale }: { children: React.ReactNode; locale: string }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <ThemeCustomizationProvider>
        <I18nProvider locale={locale}>
          {children}
        </I18nProvider>
      </ThemeCustomizationProvider>
    </NextThemesProvider>
  );
}
