import { setRequestLocale } from "next-intl/server";

export const dynamic = "force-dynamic";

export default async function WritingNewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  // 工作区由共享布局持有，设置页返回时保留当前输入。
  return null;
}
