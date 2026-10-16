"use client";

import { downloadExport } from "@/lib/userExport";

import { useEffect, useState } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { ConfirmActionModal } from "@/components/shared/RelationEditorPrimitives";
import ReplacementCharacterNotice from "@/components/shared/ReplacementCharacterNotice";
import { apiGet, apiPatch, apiPost, ApiRequestError } from "@/lib/api";
import { notifyResourceChange } from "@/lib/resourceChanges";
import type { ChangeSet, ResourceRef } from "@/types/assistant";
import { useNovelAssistant } from "./AssistantContext";

const INPUT = "w-full min-w-0 rounded-lg border border-border bg-field px-3 py-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-accent";
const LIFECYCLE_MESSAGES = {
  ASSISTANT_GENERATION_FAILED: "generationFailed",
  ASSISTANT_GENERATION_CANCELLED: "generationCancelled",
  ASSISTANT_GENERATION_INTERRUPTED: "generationInterrupted",
  ASSISTANT_REVIEW_INCOMPLETE: "reviewIncomplete",
} as const;

/** 递归编辑候选中的真实内容，保留字段类型，不复制各模块完整表单。
 * Args: value 候选值；path 字段位置；onChange 改动回调。
 * Returns: 稳定身份的候选字段编辑器。
 */
function CandidateFields({ value, path, onChange }: { value: unknown; path: string; onChange: (value: unknown) => void }) {
  const t = useTranslations("writing.assistant");
  const field = path.split(".").at(-1) ?? path;
  const label = t.has(`fields.${field}`) ? t(`fields.${field}`) : field.replaceAll("_", " ");
  if (Array.isArray(value)) return <fieldset className="min-w-0 space-y-3 border-l border-border pl-3"><legend className="mb-2 text-xs font-medium text-muted">{label}</legend>{value.map((item, index) => <CandidateFields key={`${path}.${index}`} path={`${path}.${index + 1}`} value={item} onChange={(next) => onChange(value.map((old, position) => position === index ? next : old))} />)}</fieldset>;
  if (value !== null && typeof value === "object") return <div className="min-w-0 space-y-3">{Object.entries(value).map(([key, item]) => <CandidateFields key={key} path={`${path}.${key}`} value={item} onChange={(next) => onChange({ ...value, [key]: next })} />)}</div>;
  if (typeof value === "boolean") return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />{label}</label>;
  if (value === null) return <div className="text-xs text-muted">{label}: {t("unset")}</div>;
  return <label className="grid min-w-0 gap-1 text-xs text-muted"><span>{label}</span>{typeof value === "number"
    ? <input aria-label={label} className={INPUT} type="number" value={value} onChange={(event) => onChange(event.target.valueAsNumber)} />
    : <textarea aria-label={label} className={`${INPUT} min-h-24 resize-y leading-6`} value={String(value)} onChange={(event) => onChange(event.target.value)} />}</label>;
}

/** 按字段展示候选与差异，长段落保持可读，不把数据结构当成正文。
 * Args: value 当前字段值。
 * Returns: 业务字段及其内容。
 */
function CandidateValue({ value }: { value: unknown }) {
  const t = useTranslations("writing.assistant");
  if (value == null) return <span className="text-muted">{t("unset")}</span>;
  if (Array.isArray(value)) return <ol className="space-y-2">{value.map((entry, index) => <li key={index}><CandidateValue value={entry} /></li>)}</ol>;
  if (typeof value === "object") return <dl className="space-y-2">{Object.entries(value).map(([key, entry]) => <div key={key}><dt className="text-xs text-muted">{t.has(`fields.${key}`) ? t(`fields.${key}`) : key.replaceAll("_", " ")}</dt><dd className="mt-1"><CandidateValue value={entry} /></dd></div>)}</dl>;
  return <p className="reading-copy w-full whitespace-pre-wrap break-words text-sm leading-7">{String(value)}</p>;
}

/** 展示单个独立修改组的差异、审核和精确修订确认。
 * Args: change 当前候选；onChanged 替换服务器返回的最新组。
 * Returns: 侧栏候选审核段落和必要的确认弹窗。
 */
export default function ChangeReview({ change, onChanged, onApplied, onBusyChange, disabled = false, drafts }: { change: ChangeSet; onChanged: (change: ChangeSet) => void; onApplied?: (runId?: string | null) => Promise<void>; onBusyChange?: (busy: boolean) => void; disabled?: boolean; drafts: Map<string, { revision: number; value: ChangeSet }> }) {
  const t = useTranslations("writing.assistant");
  const taskNames = useTranslations("taskFlows.tasks");
  const { novelId, navigate } = useNovelAssistant();
  const [draft, setDraft] = useState<{ revision: number; value: ChangeSet } | null>(() => drafts.get(change.id) ?? null);
  useEffect(() => { if (draft) drafts.set(change.id, draft); else drafts.delete(change.id); }, [change.id, draft, drafts]);
  const [busy, setBusy] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const [creationFailure, setCreationFailure] = useState("");
  const [confirm, setConfirm] = useState(false);
  const approvalKey = `${change.revision}:${change.confirmation?.token ?? ""}`;
  const [approvalRevision, setApprovalRevision] = useState(approvalKey);
  if (approvalRevision !== approvalKey) {
    setApprovalRevision(approvalKey); setConfirm(false);
  }
  const base = `/api/novels/${novelId}/assistant/changes/${change.id}`;
  const lifecycle = change.operations?.some((operation) => operation.action === "delete" || operation.action === "restore") ?? false;
  const important = Boolean(change.confirmation);
  const conflicts = change.review?.issues.some((issue) => issue.severity === "conflict") ?? false;
  const pending = change.status === "draft" || change.status === "reviewed";
  const saveUnknown = change.status !== "applied" && (change.apply_attempt?.outcome === "unknown"
    || (change.status === "generating" && (change.apply_attempt?.revision !== change.revision
      || !["not_sent", "not_committed"].includes(change.apply_attempt?.outcome ?? ""))));
  const creationError = change.status === "applied" ? "" : change.creation_error?.message || creationFailure;
  const readOnly = Boolean(creationError);
  const lifecycleMessage = LIFECYCLE_MESSAGES[change.program_error?.code as keyof typeof LIFECYCLE_MESSAGES];
  const currentCandidate = draft?.value ?? change;
  const act = async (action: "edit" | "review" | "apply") => {
    if (readOnly || disabled || busy) return;
    if (saveUnknown && action !== "apply") return;
    setBusy(action); onBusyChange?.(true); setError("");
    try {
      if (action === "edit" && draft) {
        const value = draft.value.kind === "operations" ? { operations: draft.value.operations } : { candidate: draft.value.candidate };
        onChanged(await apiPatch<ChangeSet>(base, { expected_revision: draft.revision, ...value }));
        setExpanded(true); setDraft(null);
      } else if (action === "review") {
        onChanged(await apiPost<ChangeSet>(`${base}/review`, { expected_revision: change.revision }));
      } else if (action === "apply") {
        const result = await apiPost<NonNullable<ChangeSet["result"]>>(`${base}/apply`, { expected_revision: change.revision, confirm_lifecycle: lifecycle, accept_content_risk: conflicts, ...(change.confirmation?.token ? { confirmation_token: change.confirmation.token } : {}) });
        onChanged({ ...change, status: "applied", result });
        notifyResourceChange({ novelId, source: "assistant", resources: result.resources });
        setConfirm(false);
        await onApplied?.(result.resume_run_id);
      }
    } catch (reason) {
      if (action === "apply") {
        // 网络响应丢失时先读回执，已经保存的组不能显示成尚未保存。
        const saved = await apiGet<ChangeSet>(base).catch(() => null);
        if (saved?.status === "applied" && saved.revision === change.revision && saved.result) {
          onChanged(saved); setConfirm(false);
          notifyResourceChange({ novelId, source: "assistant", resources: saved.result.resources });
          // 同修订原键重放，补齐已保存但尚未衔接原任务的步骤。
          const recovered = await apiPost<NonNullable<ChangeSet["result"]>>(`${base}/apply`, { expected_revision: change.revision, confirm_lifecycle: lifecycle, accept_content_risk: conflicts, ...(change.confirmation?.token ? { confirmation_token: change.confirmation.token } : {}) }).catch(() => null);
          await onApplied?.(recovered?.resume_run_id);
          return;
        }
      }
      if (reason instanceof ApiRequestError && reason.code === "ASSISTANT_CREATION_REQUEST_EXPIRED") setCreationFailure(reason.message);
      else setError(reason instanceof Error ? reason.message : t("operationFailed"));
    }
    finally { setBusy(""); onBusyChange?.(false); }
  };
  const target = change.creation_context?.target ?? change.result?.resources[0] ?? change.operations?.find((operation) => operation.id && !operation.id.startsWith("new_"));
  const childUsage = Object.values(change.child_usage ?? {});
  return <section className="min-w-0 border-t border-border py-4" aria-label={t("changeSet")} data-assistant-change={change.id}>
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <h3 className="min-w-0 flex-1 text-sm font-semibold">{change.generation_task && taskNames.has(change.generation_task) ? taskNames(change.generation_task) : t(change.status === "applied" ? "savedResult" : "pendingResult")}</h3>
      <span className="text-xs text-muted">{saveUnknown ? t("saveUnknown") : t(`changeStatus.${change.status}`)}</span>
      {target?.id && <Button size="sm" variant="ghost" onPress={() => navigate({ resource_type: target.resource_type, id: target.id! })}>{t("locate")}</Button>}
    </div>
    {pending && <ReplacementCharacterNotice value={currentCandidate.kind === "operations"
      ? { operations: currentCandidate.operations?.map((operation) => ({ fields: operation.fields })) }
      : { candidate: currentCandidate.candidate }} />}
    {draft && <p className="mb-2 text-xs text-muted">{t("resumeDraft")}</p>}
    {creationError && <p role="alert" className="mb-2 text-sm text-danger">{creationError}</p>}
    {change.program_error && !saveUnknown && change.status !== "applied" && <p role="alert" className="mb-2 text-sm text-danger">{lifecycleMessage ? t(lifecycleMessage) : change.program_error.message}</p>}
    <Button size="sm" variant="ghost" aria-expanded={expanded || Boolean(draft)} onPress={() => setExpanded((value) => !value)}>{t("viewChanges")}</Button>
    {(lifecycle || conflicts || important) && pending && <div className="my-2 space-y-2">
      {change.confirmation && <><p className="text-sm">{change.confirmation.message}</p><ul className="text-sm">{change.confirmation.targets.map((item, index) => <li key={index}>{t(`actions.${item.action}`)} · {item.name}{(item.action === "delete" || item.action === "restore") ? <p className="text-sm text-muted">{t(item.action === "delete" ? "recycleEffect" : "restoreEffect")}</p> : item.fields && <dl className="space-y-2 border-l border-border pl-3">{Object.entries(item.fields).map(([field, values]) => <div key={field}><dt className="font-medium">{t.has(`fields.${field}`) ? t(`fields.${field}`) : field}</dt><dd><span className="text-xs text-muted">{t("before")}</span><CandidateValue value={values.before} /><span className="text-xs text-muted">{t("after")}</span><CandidateValue value={values.after} /></dd></div>)}</dl>}</li>)}</ul></>}
      {change.review?.issues.filter((issue) => issue.severity === "conflict").map((issue, index) => <p key={index} className="text-sm text-danger">{issue.message}</p>)}
      <Button size="sm" variant="outline" isDisabled={disabled || Boolean(busy) || readOnly || change.status !== "reviewed"} onPress={() => { if (change.confirmation?.token) void act("apply"); else setConfirm(true); }}>{t(change.confirmation?.token ? "confirmAndContinue" : "confirmTitle")}</Button>
    </div>}
    {(expanded || Boolean(draft)) && <div className="mt-2">
    {change.undo_of && <p className="mb-2 text-xs text-muted">{t("undoCandidate")}</p>}
    {change.creation_context && <p className="mb-2 text-xs text-muted">{t(change.creation_context.semantics === "position_writing" ? "positionWritingCandidate" : "bookManagementCandidate")}</p>}
    {childUsage.length > 0 && <p className="mb-2 text-xs text-muted">{t("childUsage", { calls: childUsage.reduce((sum, item) => sum + item.model_calls, 0), tokens: childUsage.reduce((sum, item) => sum + item.usage.total_tokens, 0) })}{childUsage.some((item) => !item.usage_complete) ? ` · ${t("usageIncomplete")}` : ""}</p>}
    {draft ? <div className="space-y-4"><fieldset disabled={readOnly || saveUnknown} className="min-w-0 space-y-4">
      {draft.value.kind === "operations" ? draft.value.operations?.map((operation, index) => <fieldset key={index} className="min-w-0 space-y-3">
        <legend className="mb-2 text-sm font-medium">{t(`actions.${operation.action}`)} · {t(`kinds.${operation.resource_type}`)}</legend>
        <CandidateFields path="fields" value={operation.fields} onChange={(fields) => setDraft({ ...draft, value: { ...draft.value, operations: draft.value.operations!.map((old, position) => position === index ? { ...old, fields: fields as Record<string, unknown> } : old) } })} />
      </fieldset>) : <CandidateFields path="candidate" value={draft.value.candidate} onChange={(candidate) => setDraft({ ...draft, value: { ...draft.value, candidate: candidate as Record<string, unknown> } })} />}
    </fieldset><div className="flex flex-wrap gap-2"><Button size="sm" variant="primary" isDisabled={disabled || Boolean(busy) || readOnly || saveUnknown} onPress={() => void act("edit")}>{t("saveCandidate")}</Button><Button size="sm" variant="ghost" isDisabled={disabled || Boolean(busy)} onPress={() => setDraft(null)}>{t("cancel")}</Button></div>
    </div> : <>
      {change.diffs?.map((diff, index) => <div key={index} className="mb-3 min-w-0 space-y-2">
        <p className="text-xs font-medium text-muted">{t(`actions.${diff.action}`)} · {t(`kinds.${diff.resource_type}`)}</p>
        <p className="reading-copy text-sm">{diff.reason}</p>
        {Object.entries(diff.after).map(([field, value]) => <details key={field} className="min-w-0 border-l border-border pl-3" open={Object.keys(diff.after).length === 1}>
          <summary className="cursor-pointer py-1 text-sm font-medium">{t.has(`fields.${field}`) ? t(`fields.${field}`) : field.replaceAll("_", " ")}</summary>
          <div className="space-y-2 py-2 text-sm"><div><span className="text-xs text-muted">{t("before")}</span><CandidateValue value={diff.before[field]} /></div>
          <div className="border-l-2 border-accent pl-3"><span className="text-xs text-muted">{t("after")}</span><CandidateValue value={value} /></div></div>
        </details>)}
      </div>)}
      {change.candidate && <details className="min-w-0" open><summary className="cursor-pointer text-sm">{t("candidate")}</summary><div className="mt-2"><CandidateValue value={change.candidate} /></div></details>}
      {change.review && <div className="mt-3 min-w-0 space-y-2 border-l-2 border-border pl-3">
        <p className="reading-copy text-sm">{change.review.summary}</p>
        {change.review.issues.map((issue, index) => <div key={index} className="text-sm"><span className={issue.severity === "conflict" ? "font-semibold text-danger" : "font-medium text-muted"}>{t(`issue.${issue.severity}`)}</span><p className="reading-copy">{issue.message}</p>
          {issue.sources.map((source) => <Button key={`${source.resource_type}:${source.id}`} size="sm" variant="ghost" onPress={() => navigate(source)}>{t("source", { kind: t(`kinds.${source.resource_type}`), id: source.id })}</Button>)}</div>)}
        <p className="text-xs text-muted">{t("reviewScope", { count: change.source_refs?.length ?? 0 })}</p>
        {Boolean(change.review.omitted_fields.length) && <p className="text-xs text-muted">{t("omitted", { count: change.review.omitted_fields.length })}</p>}
      </div>}
      {change.source_refs && change.source_refs.length > 0 && <details className="mt-3"><summary className="cursor-pointer text-xs text-muted">{t("sources", { count: change.source_refs.length })}</summary><div className="mt-2 flex flex-wrap gap-1">{change.source_refs.map((source: ResourceRef) => <Button key={`${source.resource_type}:${source.id}`} size="sm" variant="ghost" onPress={() => navigate(source)}>{t("source", { kind: t(`kinds.${source.resource_type}`), id: source.id })}</Button>)}</div></details>}
      {change.status === "applied" && change.result && <div className="mt-3 flex flex-wrap gap-1">{change.result.resources.map((resource) => <Button key={`${resource.resource_type}:${resource.id}`} size="sm" variant="ghost" onPress={() => navigate(resource)}>{t("source", { kind: t(`kinds.${resource.resource_type}`), id: resource.id })}</Button>)}</div>}
      <details className="mt-3"><summary className="cursor-pointer text-xs text-muted">{t("advancedChanges")}</summary><div className="mt-2 flex flex-wrap items-center gap-2">
        {pending && change.kind !== "facts" && <><Button size="sm" variant="ghost" isDisabled={disabled || Boolean(busy) || readOnly || saveUnknown} onPress={() => { setDraft({ revision: change.revision, value: structuredClone(change) }); setError(""); }}>{t("editCandidate")}</Button><Button size="sm" variant="outline" isDisabled={disabled || Boolean(busy) || readOnly || saveUnknown} onPress={() => void act("review")}>{t(busy === "review" ? "reviewing" : "review")}</Button><Button size="sm" variant="primary" isDisabled={disabled || Boolean(busy) || readOnly || change.status !== "reviewed"} onPress={() => { setError(""); if (change.confirmation?.token) void act("apply"); else setConfirm(true); }}>{t("apply")}</Button></>}

      </div></details>
    </>}
    {(pending || readOnly) && <Button className="mt-2" size="sm" variant="ghost" onPress={() => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(currentCandidate, null, 2)], { type: "application/json;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = `assistant-proposal-${change.id}.json`; void downloadExport(link); URL.revokeObjectURL(url);
    }}>{t("exportCandidate")}</Button>}
    </div>}
    {error && !confirm && <p role="alert" className="mt-2 break-words text-sm text-danger">{error}</p>}
    {confirm && <ConfirmActionModal title={t("confirmTitle")} message={<div className="space-y-3"><ul>{(change.confirmation?.targets ?? change.operations?.map((item) => ({ name: item.fields.name ?? item.fields.title ?? item.id, action: item.action })) ?? []).map((item, index) => <li key={index}>{t(`actions.${item.action}`)} · {String(item.name ?? "")}</li>)}</ul>
      {lifecycle && <p>{t("confirmLifecycle")}</p>}
      {conflicts && <>{change.review?.issues.filter((issue) => issue.severity === "conflict").map((issue, index) => <p key={index}>{issue.message}</p>)}<p>{t("acceptRisk")}</p></>}
    </div>} confirmText={t("apply")} cancelText={t("cancel")} isLoading={busy === "apply"} error={error || creationError} isConfirmDisabled={readOnly} onCancel={() => { setConfirm(false); setError(""); }} onConfirm={() => void act("apply")} />}
  </section>;
}
