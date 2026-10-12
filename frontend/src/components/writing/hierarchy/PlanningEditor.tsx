"use client";
import { useAssistantResource } from "../assistant/AssistantContext";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { apiGet, apiPost, apiPut, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import { RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import { SectionActionButton } from "@/components/shared/SectionEditButton";
import DocumentSection from "@/components/shared/DocumentSection";
import { emptyPlanningDraft, hierarchyChildrenUrl, type EntityChoices, type HierarchyNode, type HierarchyRecord, type PlanningDraft, type PlanningKind } from "@/types/hierarchy";
import PlanningFields, { PlanningReadout, PLANNING_SECTIONS, REFERENCE_FIELDS, type PlanningSection } from "./PlanningFields";

/** 功能：创建计划或在详情中编辑一节，失败保留输入和原版本。Args: props 层级、父节点、原记录、分节、实体选项及回调。Returns: 创建弹窗或原位置表单。 */
export default function PlanningEditor({ kind, parent, source, choices, choicesError, section, onSaved, onClose, onDirty, onSavingChange }: {
  kind: PlanningKind; parent: HierarchyNode; source: HierarchyNode | null; choices: EntityChoices; choicesError?: string;
  section?: PlanningSection; onSaved: (record: HierarchyRecord) => void; onClose: () => void; onDirty?: (dirty: boolean) => void; onSavingChange?: (saving: boolean) => void;
}) {
  const t = useTranslations("writing.hierarchy");
  const [draft, setDraft] = useState<PlanningDraft>(() => source ? { title: source.record.title, summary: source.record.summary, planning: source.record.planning as PlanningDraft["planning"] } : emptyPlanningDraft(kind));
  const [version, setVersion] = useState(source?.record.version ?? parent.record.version);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<ApiFieldErrors>({});
  const [conflict, setConflict] = useState<HierarchyRecord | null>(null);
  const [baseRecord, setBaseRecord] = useState(source?.record ?? null);
  const writes = useRef(Promise.resolve());
  const finished = useRef(false);
  const draftLoaded = useRef(false);
  const fieldsRef = useRef<HTMLDivElement>(null);
  const initialFocusDone = useRef(false);
  const command = useRef<{ payload: string; key: string } | null>(null);
  const key = `${parent.record.novel_id}:${kind}:${source?.id ?? `new:${parent.id}`}:plan${section ? `:${section}` : ""}`;

  useAssistantResource(source ? { resource_type: kind, id: source.id, name: source.record.title, version: source.record.version, draft: { text: JSON.stringify(draft), fields: ["title", "summary", "planning"], version } } : null);

  useEffect(() => {
    let active = true;
    type StoredPlan = { draft: PlanningDraft; command: { payload: string; key: string } | null };
    readWritingDraft<StoredPlan>(key, source?.record.version ?? parent.record.version).then((stored) => {
      if (!active) return;
      draftLoaded.current = true;
      if (!stored) return;
      setDraft(stored.value.draft); command.current = stored.value.command;
      setVersion(stored.base_version);
      if (source && stored.base_version !== source.record.version) setConflict(source.record);
    }).catch(() => { if (active) setError(t("draftFailed")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [key, source, parent.record.version, t]);

  useEffect(() => {
    if (loading || saving || finished.current || !draftLoaded.current) return;
    writes.current = writes.current.then(() => writeWritingDraft(key, version, { draft, command: command.current }))
      .catch(() => setError(t("draftFailed")));
  }, [draft, key, loading, saving, t, version]);

  useEffect(() => {
    onDirty?.(!loading && JSON.stringify(draft) !== JSON.stringify(source ? { title: source.record.title, summary: source.record.summary, planning: source.record.planning } : emptyPlanningDraft(kind)));
    return () => onDirty?.(false);
  }, [draft, kind, loading, onDirty, source]);

  useEffect(() => {
    onSavingChange?.(saving);
    return () => onSavingChange?.(false);
  }, [onSavingChange, saving]);

  useEffect(() => {
    if (!section || loading || initialFocusDone.current) return;
    const frame = requestAnimationFrame(() => {
      fieldsRef.current?.querySelector<HTMLElement>("input:not(:disabled), textarea:not(:disabled), select:not(:disabled)")?.focus();
      initialFocusDone.current = true;
    });
    return () => cancelAnimationFrame(frame);
  }, [loading, section]);

  const save = async () => {
    setSaving(true); setError(""); setErrors({});
    // 多行列表只在提交时去掉空行，编辑期间保留换行和输入焦点。
    const planning = Object.fromEntries(Object.entries(draft.planning).map(([field, value]) => [field, Array.isArray(value) ? value.map((item) => item.trim()).filter(Boolean) : value]));
    // 后端 planning 是完整对象，只替换当前节，避免把另一节的旧草稿一并保存。
    const payload = section === "identity" ? { title: draft.title, summary: draft.summary }
      : section ? { planning: { ...baseRecord?.planning, ...Object.fromEntries(Object.entries(planning).filter(([field]) => section === "references" ? REFERENCE_FIELDS.includes(field) : !REFERENCE_FIELDS.includes(field))) } }
        : { ...draft, planning };
    try {
      const serialized = JSON.stringify(payload);
      if (command.current?.payload !== serialized) command.current = { payload: serialized, key: crypto.randomUUID() };
      // 先落本地请求键，刷新或响应丢失后仍能重试同一次创建。
      await writes.current;
      await writeWritingDraft(key, version, { draft, command: command.current });
      const record = source
        ? await apiPut<HierarchyRecord>(`/api/${kind}s/${source.id}`, { ...payload, expected_version: version })
        : await apiPost<HierarchyRecord>(hierarchyChildrenUrl(parent), payload, { headers: { "Idempotency-Key": command.current.key } });
      await writes.current;
      await writeWritingDraft(key, version, null).catch(() => setError(t("draftFailed")));
      finished.current = true;
      onSaved(record);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : t("saveFailed"));
      if (failure instanceof ApiRequestError) {
        setErrors(failure.fieldErrors);
        if (!section) focusRelationEditorError(failure.fieldErrors);
        if (source && failure.status === 409) {
          try { setConflict(await apiGet<HierarchyRecord>(`/api/${kind}s/${source.id}`)); }
          catch (readError) { setError(readError instanceof Error ? readError.message : t("loadFailed")); }
        }
      }
    } finally { setSaving(false); }
  };

  useEffect(() => {
    if (!section || !error || saving) return;
    const frame = requestAnimationFrame(() => {
      const firstField = Object.keys(errors)[0]?.split(".").at(-1);
      const field = firstField ? fieldsRef.current?.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`) : null;
      const target = field ?? fieldsRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [error, errors, saving, section]);

  const fields = <>
          {error && <RelationEditorErrorSummary message={error} fieldErrors={errors} className="mb-4" />}
          {choicesError && <RelationEditorErrorSummary message={choicesError} className="mb-4" />}
          {conflict && <div role="alert" className="mb-5 border-y border-amber-500/50 py-3">
            <p className="text-sm">{t("conflict")}</p>
            <details className="my-2"><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("latestPlan")}</summary><h3 className="font-semibold">{conflict.title}</h3><PlanningReadout record={conflict} choices={choices} /></details>
            <Button size="sm" variant="outline" onPress={() => { void (async () => {
              await writes.current;
              await writeWritingDraft(key, version, null).catch(() => setError(t("draftFailed")));
              setBaseRecord(conflict); setVersion(conflict.version); setConflict(null); setError("");
            })(); }}>{t("useLatestVersion")}</Button>
          </div>}
          {loading ? <p role="status">{t("loading")}</p> : <PlanningFields kind={kind} value={draft} onChange={setDraft} choices={choices} disabled={saving} errors={errors} section={section} />}
  </>;
  const cancel = () => { void (async () => {
            setSaving(true);
            try {
              await writes.current;
              await writeWritingDraft(key, version, null);
              if (section) { finished.current = true; onClose(); return; }
              setDraft(source ? { title: source.record.title, summary: source.record.summary, planning: source.record.planning as PlanningDraft["planning"] } : emptyPlanningDraft(kind));
              setVersion(source?.record.version ?? parent.record.version); command.current = null; setConflict(null); setError(""); setErrors({});
            } catch { setError(t("draftFailed")); }
            finally { setSaving(false); }
          })(); };
  const actions = <>
          {!section && <Button size="sm" variant="ghost" isDisabled={saving} onPress={onClose}>{t("closeKeepDraft")}</Button>}
          {section ? <SectionActionButton action="cancel" label={t("sectionCancel")} isDisabled={loading || saving} onPress={cancel} /> : <Button size="sm" variant="ghost" isDisabled={loading || saving} onPress={cancel}>{t("discardLocalDraft")}</Button>}
          {section ? <SectionActionButton action="save" label={saving ? t("saving") : t("sectionSave")} isDisabled={loading || saving || Boolean(conflict)} onPress={() => void save()} /> : <Button size="sm" variant="primary" isDisabled={loading || saving || Boolean(conflict)} onPress={() => void save()}>{saving ? t("saving") : t("savePlan")}</Button>}
  </>;

  if (section) return <DocumentSection number={String(PLANNING_SECTIONS.indexOf(section) + 1).padStart(2, "0")} title={t(`sections.${section}`)} actions={actions}><div ref={fieldsRef}>{fields}</div></DocumentSection>;
  return <RetainedModalBackdrop isOpen onOpenChange={(open) => !open && !saving && onClose()} isDismissable={!saving} isKeyboardDismissDisabled={saving}>
    <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
      <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-4xl">
        <Modal.Header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-7">
          <Modal.Heading className="text-lg font-semibold">{t(source ? "editKind" : "createKind", { kind: t(`kinds.${kind}`) })}</Modal.Heading>
          <Modal.CloseTrigger aria-label={t("close")} isDisabled={saving} />
        </Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 px-5 py-5 sm:px-7">
          <p className="mb-5 text-sm text-muted">{t("parent", { title: parent.record.title })}</p>
          {fields}
        </Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">{actions}</Modal.Footer>
      </Modal.Dialog>
    </Modal.Container>
  </RetainedModalBackdrop>;
}
