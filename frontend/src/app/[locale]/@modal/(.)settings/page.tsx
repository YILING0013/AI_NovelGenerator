import { setRequestLocale } from "next-intl/server";
import SettingsContent from "@/components/settings/SettingsContent";

export const dynamic = "force-dynamic";

export default async function SettingsModalPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <SettingsContent presentation="modal" />;
}