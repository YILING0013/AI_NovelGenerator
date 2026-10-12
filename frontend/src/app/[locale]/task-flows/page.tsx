import { Suspense } from "react";
import { setRequestLocale } from "next-intl/server";
import TaskFlowWorkspace from "@/components/task-flows/TaskFlowWorkspace";

export const dynamic = "force-dynamic";

/** 功能：提供任务流程配置页。Args: params 当前语言。Returns: 配置工作台。 */
export default async function TaskFlowsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <Suspense><TaskFlowWorkspace /></Suspense>;
}
