import { setRequestLocale } from "next-intl/server";

export const dynamic = "force-dynamic";

export default async function WritingEditPage({
  params,
}: {
  params: Promise<{ locale: string; novelId: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  // 工作区由共享布局按小说 ID 持有。
  return null;
}
