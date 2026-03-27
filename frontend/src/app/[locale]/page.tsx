import { setRequestLocale } from "next-intl/server";
import BookshelfContent from "@/components/bookshelf/BookshelfContent";

export const dynamic = "force-dynamic";

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <BookshelfContent />;
}
