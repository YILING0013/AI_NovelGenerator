import { setRequestLocale } from "next-intl/server";
import WritingContent from "@/components/writing/WritingContent";

export const dynamic = "force-dynamic";

export default async function WritingNewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <WritingContent mode="create" />;
}
