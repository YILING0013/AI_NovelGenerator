import { setRequestLocale } from "next-intl/server";
import WritingContent from "@/components/writing/WritingContent";

export const dynamic = "force-dynamic";

export default async function WritingEditPage({
  params,
}: {
  params: Promise<{ locale: string; novelId: string }>;
}) {
  const { locale, novelId } = await params;
  setRequestLocale(locale);
  return <WritingContent mode="edit" novelId={novelId} />;
}
