import { hasLocale } from "next-intl";
import { notFound } from "next/navigation";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { NextIntlClientProvider } from "next-intl";
import { routing } from "@/i18n/routing";
import { Providers } from "./providers";
import { StartupGate } from "@/components/layout/StartupGate";
import Navbar from "@/components/layout/Navbar";
import { WorkspacePages } from "@/components/layout/WorkspacePages";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "nav" });
  return { title: t("title") };
}

export default async function LocaleLayout({
  children,
  modal,
  params,
}: {
  children: React.ReactNode;
  modal: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  setRequestLocale(locale);

  const messages = await getMessages();

  return (
    <html lang={locale} className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <NextIntlClientProvider messages={messages}>
          <Providers locale={locale}>
            <StartupGate>
              <Navbar />
              <main className="flex min-h-0 flex-1 flex-col"><WorkspacePages>{children}</WorkspacePages></main>
              {modal}
            </StartupGate>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
