import { setRequestLocale } from "next-intl/server";

export const dynamic = "force-dynamic";

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  // 工作区由共享布局持有，离开页面时仍可继续生成。
  return null;
}
