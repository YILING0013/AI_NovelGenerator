"use client";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";
import SectionEditButton from "@/components/shared/SectionEditButton";


import { TaskFlowForm,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";

import { Button,Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
useEffect,
useMemo,
useReducer,
useRef,
useState,
} from "react";

import {
RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import ItemFieldsForm from "@/components/writing/items/ItemFieldsForm";
import {
buildCandidateExpectedVersions,
createLocalCandidateState,
localCandidateReducer,
} from "@/lib/aiCandidate";
import {
ApiRequestError,
type ApiFieldErrors
} from "@/lib/api";
import type { CharacterResponseV1 } from "@/types/character";
import {
parseItemsCandidateEnvelopeV1,
type ItemBulkGeneratedRequestV1,
type ItemCandidateV1,
type ItemReadV1,
type ItemsBasisV1,
type ItemsCandidateEnvelopeV1,
type ItemsResultV1
} from "@/types/item";
import type { LocationReadV1 } from "@/types/location";
import type { CoreFaction } from "@/types/novel";

interface ItemCandidateWorkspaceProps {
  novelId: string;
  items: ItemReadV1[];
  characters: Array<Pick<CharacterResponseV1, "character_id" | "name" | "status" | "is_deleted">>;
  factions: Array<Pick<CoreFaction, "faction_id" | "name" | "active_status" | "is_deleted">>;
  locations: LocationReadV1[];
  disabled?: boolean;
  onReviewingChange?: (reviewing: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
  onPrepare: (request: ItemBulkGeneratedRequestV1) => Promise<void>;
}

function validateCandidate(
  candidate: ItemCandidateV1,
  duplicateName: boolean,
  messages: {
    name: string;
    type: string;
    description: string;
    storyFunction: string;
    held: string;
    terminal: string;
    entryTooLong: string;
    duplicateName: string;
  },
): ApiFieldErrors {
  const errors: ApiFieldErrors = {};
  if (!candidate.name.trim()) errors.name = [messages.name];
  else if (duplicateName) errors.name = [messages.duplicateName];
  if (!candidate.item_type.trim()) errors.item_type = [messages.type];
  if (!candidate.description.trim()) errors.description = [messages.description];
  if (!candidate.story_function.trim()) errors.story_function = [messages.storyFunction];
  if (candidate.lifecycle_status === "held" && !candidate.owner_character_id && !candidate.controlling_faction_id) {
    errors.lifecycle_status = [messages.held];
  }
  if (["destroyed", "consumed"].includes(candidate.lifecycle_status) && (
    candidate.owner_character_id || candidate.controlling_faction_id || candidate.current_location_id
  )) {
    errors.lifecycle_status = [messages.terminal];
  }
  for (const [field, values] of ([
    ["abilities", candidate.abilities],
    ["limitations", candidate.limitations],
    ["costs", candidate.costs],
  ] as const)) {
    if (values.some((value) => value.length > 500)) errors[field] = [messages.entryTooLong];
  }
  return errors;
}

function focusCandidateError(fieldErrors: ApiFieldErrors) {
  requestAnimationFrame(() => {
    const workspace = document.querySelector<HTMLElement>('[aria-labelledby="item-candidate-heading"]');
    if (!workspace) return;
    const firstField = Object.keys(fieldErrors)[0]?.split(".").at(-1);
    const field = firstField
      ? workspace.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`)
      : null;
    const target = field ?? workspace.querySelector<HTMLElement>("[data-editor-error-summary]");
    target?.focus({ preventScroll: true });
    target?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  });
}

/**
 * 显示物品 AI 参数、生成进度和当前页面内的候选复核。
 *
 * Args:
 *   novelId: 当前小说 ID。
 *   items: 页面当前加载的正式物品。
 *   characters: 可引用的角色。
 *   factions: 可引用的势力。
 *   locations: 可引用的地点。
 *   disabled: 是否暂时禁止生成和确认。
 *   onReviewingChange: 进入或离开候选复核时通知父工作台。
 *   onBusyChange: 生成或保存期间通知父工作台锁定正式操作。
 *   onPrepare: 完整批次落入起点准备稿后才离开候选编辑。
 *
 * Returns:
 *   AI 生成按钮、参数窗口或候选主从工作台。
 */
export default function ItemCandidateWorkspace({
  novelId,
  items,
  characters,
  factions,
  locations,
  disabled = false,
  onReviewingChange,
  onBusyChange,
  onPrepare,
}: ItemCandidateWorkspaceProps) {
  const t = useTranslations("writing.items.ai");
  const itemT = useTranslations("writing.items");
  const taskFlow = useTaskFlow("create_items_by_ai");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [candidateState, dispatchCandidate] = useReducer(
    localCandidateReducer<ItemsResultV1>,
    createLocalCandidateState<ItemsResultV1>(),
  );
  const [selectedCandidateRef, setSelectedCandidateRef] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [candidateFieldErrors, setCandidateFieldErrors] = useState<Record<string, ApiFieldErrors>>({});
  const generationAbortRef = useRef<AbortController | null>(null);
  const previewPageVersionsRef = useRef<Record<string, number>>({});
  const dialogReturnFocusRef = useRef<HTMLElement | null>(null);
  const currentNovelIdRef = useRef(novelId);
  currentNovelIdRef.current = novelId;

  const candidates = candidateState.candidate?.items ?? [];
  const selectedCandidate = candidates.find((candidate) => candidate.candidate_ref === selectedCandidateRef)
    ?? candidates[0]
    ?? null;
  const reviewing = Boolean(candidateState.candidate);
  const busy = candidateState.status === "generating" || candidateState.status === "confirming";
  const readOnly = disabled || candidateState.status === "stale" || candidateState.status === "confirming";

  const currentKnownVersions = useMemo(() => {
    const versions: Record<string, number> = {};
    for (const item of items) versions[`item:${item.item_id}`] = item.version;
    for (const location of locations) versions[`location:${location.location_id}`] = location.version;
    return versions;
  }, [items, locations]);
  const currentKnownVersionsRef = useRef(currentKnownVersions);
  currentKnownVersionsRef.current = currentKnownVersions;

  useEffect(() => {
    onReviewingChange?.(reviewing);
  }, [onReviewingChange, reviewing]);

  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  useEffect(() => () => onBusyChange?.(false), [onBusyChange]);

  useEffect(() => {
    const basis = candidateState.basis;
    if (!basis || candidateState.status === "stale") return;
    const knownTypes = new Set(["item", "location"]);
    const changed = basis.source_refs.some((source) => {
      const key = `${source.resource_type}:${source.id}`;
      const before = previewPageVersionsRef.current[key];
      if (!knownTypes.has(source.resource_type) || before === undefined) return false;
      const current = currentKnownVersions[key];
      return current !== before && (current === undefined || current !== source.version);
    });
    if (changed) dispatchCandidate({ type: "mark_stale" });
  }, [candidateState.basis, candidateState.status, currentKnownVersions]);

  useEffect(() => {
    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    dispatchCandidate({ type: "discard" });
    setDialogOpen(false);
    setSelectedCandidateRef("");
    setCandidateFieldErrors({});
    previewPageVersionsRef.current = {};
    return () => {
      generationAbortRef.current?.abort();
    };
  }, [novelId]);

  const closeGenerationDialog = () => {
    setDialogOpen(false);
    requestAnimationFrame(() => dialogReturnFocusRef.current?.focus());
  };

  const discardCandidate = () => {
    void taskFlow.discard();

    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    dispatchCandidate({ type: "discard" });
    setSelectedCandidateRef("");
    setMobileDetailOpen(false);
    setCandidateFieldErrors({});
    previewPageVersionsRef.current = {};
  };

  const generate = async (retry: TaskFlowRunMode = false) => {
    if (disabled || generationAbortRef.current || candidateState.candidate) return;
    const requestId = candidateState.requestId + 1;
    const requestNovelId = novelId;
    const controller = new AbortController();
    generationAbortRef.current = controller;
    dispatchCandidate({ type: "generate", requestId });
    setDialogOpen(false);
    try {
      const generated = await taskFlow.run(`/api/llm/novels/${novelId}/items/stream`, { novel_id: requestNovelId }, controller.signal, retry);
      if (controller.signal.aborted || generationAbortRef.current !== controller || currentNovelIdRef.current !== requestNovelId) return;
      const envelope: ItemsCandidateEnvelopeV1 | null = parseItemsCandidateEnvelopeV1(generated.result, requestNovelId);
      if (!envelope) throw new Error(t("errors.invalidPreview"));
      dispatchCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      previewPageVersionsRef.current = Object.fromEntries(
        envelope.basis.source_refs.flatMap((source) => {
          const key = `${source.resource_type}:${source.id}`;
          const pageVersion = currentKnownVersionsRef.current[key];
          return pageVersion === undefined ? [] : [[key, pageVersion]];
        }),
      );
      setSelectedCandidateRef(envelope.candidate.items[0]?.candidate_ref ?? "");
      setCandidateFieldErrors({});
    } catch (error) {
      if (!controller.signal.aborted && currentNovelIdRef.current === requestNovelId) {
        let message = t("errors.generate");
        if (error instanceof ApiRequestError) {
          if (error.code?.startsWith("AGENT_")) message = error.message;
          else if (error.status === 422) message = t("errors.validation");
          else if (error.status === 502) message = t("errors.invalidPreview");
          else if (error.status === 503) message = t("errors.providerUnavailable");
          else if (error.status === 504) message = t("errors.timeout");
        } else if (error instanceof Error && error.message === t("errors.invalidPreview")) {
          message = t("errors.invalidPreview");
        }
        dispatchCandidate({ type: "generation_failed", requestId, message });
      }
    } finally {
      if (generationAbortRef.current === controller) generationAbortRef.current = null;
    }
  };

  const updateCandidate = (fields: Omit<ItemCandidateV1, "candidate_ref">) => {
    if (!candidateState.candidate || !selectedCandidate || readOnly) return;
    dispatchCandidate({
      type: "edit",
      candidate: {
        items: candidates.map((candidate) => candidate.candidate_ref === selectedCandidate.candidate_ref
          ? { ...fields, candidate_ref: candidate.candidate_ref }
          : candidate),
      },
    });
    setCandidateFieldErrors((current) => ({ ...current, [selectedCandidate.candidate_ref]: {} }));
  };

  const removeCandidate = (candidateRef: string) => {
    if (!candidateState.candidate || readOnly) return;
    const currentIndex = candidates.findIndex((candidate) => candidate.candidate_ref === candidateRef);
    const remaining = candidates.filter((candidate) => candidate.candidate_ref !== candidateRef);
    dispatchCandidate({ type: "edit", candidate: { items: remaining } });
    setCandidateFieldErrors((current) => {
      const next = { ...current };
      delete next[candidateRef];
      return next;
    });
    setSelectedCandidateRef(remaining[Math.min(currentIndex, remaining.length - 1)]?.candidate_ref ?? "");
    if (remaining.length === 0) setMobileDetailOpen(false);
  };

  const confirmCandidates = async () => {
    if (!candidateState.candidate || !candidateState.basis || candidates.length === 0 || readOnly) return;
    const normalizedNames = candidates.map((candidate) => candidate.name.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase());
    const errorsByRef: Record<string, ApiFieldErrors> = {};
    for (const candidate of candidates) {
      const normalizedName = candidate.name.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
      const errors = validateCandidate(
        candidate,
        normalizedName.length > 0 && normalizedNames.filter((name) => name === normalizedName).length > 1,
        {
          name: itemT("validation.nameRequired"),
          type: itemT("validation.typeRequired"),
          description: itemT("validation.descriptionRequired"),
          storyFunction: t("validation.storyFunctionRequired"),
          held: itemT("validation.heldRequiresHolder"),
          terminal: t("validation.terminalReferences"),
          entryTooLong: itemT("validation.entryTooLong"),
          duplicateName: t("validation.duplicateName"),
        },
      );
      if (Object.keys(errors).length > 0) errorsByRef[candidate.candidate_ref] = errors;
    }
    const firstInvalid = candidates.find((candidate) => errorsByRef[candidate.candidate_ref]);
    if (firstInvalid) {
      setCandidateFieldErrors(errorsByRef);
      setSelectedCandidateRef(firstInvalid.candidate_ref);
      setMobileDetailOpen(true);
      dispatchCandidate({ type: "confirm_failed", message: t("errors.validation") });
      focusCandidateError(errorsByRef[firstInvalid.candidate_ref]);
      return;
    }

    const basis = candidateState.basis as ItemsBasisV1;
    const request: ItemBulkGeneratedRequestV1 = {
      candidates,
      basis,
      expected_versions: buildCandidateExpectedVersions(basis),
    };
    dispatchCandidate({ type: "confirm" });
    try {
      await onPrepare(request);
      dispatchCandidate({ type: "discard" });
      setSelectedCandidateRef(""); setMobileDetailOpen(false); previewPageVersionsRef.current = {};
    } catch (error) { dispatchCandidate({ type: "confirm_failed", message: (error as Error).message }); }
  };

  if (!reviewing) {
    return (
      <div className="contents">
        <section className="workspace-toolbar ml-auto flex flex-wrap items-end gap-2" aria-labelledby="item-ai-heading">
          <h2 id="item-ai-heading" className="sr-only">{t("actions.open")}</h2>
          {candidateState.status === "generating" ? (
            <Button variant="outline" size="sm" onPress={discardCandidate}>{t("actions.cancelGeneration")}</Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onPress={() => {
                dialogReturnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
                setDialogOpen(true);
              }}
              isDisabled={disabled}
            >
              {t("actions.open")}
            </Button>
          )}
        </section>
        {candidateState.status === "error" && candidateState.error && (
          <div className="w-full border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">{candidateState.error}</div>
        )}

        {(candidateState.status === "generating" || candidateState.status === "error") && <TaskFlowProgress flow={taskFlow} running={candidateState.status === "generating"} failed={candidateState.status === "error" && candidateState.candidate === null} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={discardCandidate} label={t("progress.starting")} />}
      {dialogOpen && (
          <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && closeGenerationDialog()} variant="blur" isDismissable>
            <Modal.Container size="lg" scroll="inside" className="p-0 sm:p-4">
              <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
                <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                  <Modal.Heading className="text-lg font-semibold text-foreground">{t("dialog.title")}</Modal.Heading>
                  <Modal.CloseTrigger aria-label={t("actions.cancel")} />
                </Modal.Header>
                <Modal.Body className="px-5 py-6 sm:px-7"><TaskFlowForm flow={taskFlow} /></Modal.Body>
                <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                  <Button variant="ghost" size="sm" onPress={closeGenerationDialog}>{t("actions.cancel")}</Button>
                  <Button variant="primary" size="sm" onPress={() => void generate()} isDisabled={disabled || taskFlow.loading || !taskFlow.definition}>{t("actions.generate")}</Button>
                </Modal.Footer>
              </Modal.Dialog>
            </Modal.Container>
          </RetainedModalBackdrop>
        )}
      </div>
    );
  }

  return (
    <section className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden border-y border-border bg-surface" aria-labelledby="item-candidate-heading">
      <header className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 id="item-candidate-heading" className="text-lg font-semibold text-foreground">{t("preview.title")}</h2>
            <p className="text-xs tabular-nums text-muted">{t("preview.count", { count: candidates.length })}</p>
          </div>
          <span className="self-start rounded-full bg-surface-secondary px-2.5 py-1 text-xs tabular-nums text-muted">{t(`status.${candidateState.status}`)}</span>
        </div>
        {candidateState.status === "stale" && <div className="mt-4 border-y border-amber-400/60 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200" role="alert">{t("errors.conflict")}</div>}
        {candidateState.status !== "stale" && candidateState.error && <RelationEditorErrorSummary message={candidateState.error} className="mt-4" />}
      </header>

      {selectedCandidate ? (
        <div className="grid min-h-0 flex-1 overflow-hidden @min-[800px]/master:grid-cols-[260px_minmax(0,1fr)]">
          <aside className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} workspace-scrollbar min-h-0 overflow-y-auto bg-surface-secondary/45 border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:border-b-0 @min-[800px]/master:border-r`} tabIndex={0} aria-label={t("preview.rosterLabel")}>
            <ul className="divide-y divide-border">
              {candidates.map((candidate) => (
                <li key={candidate.candidate_ref}>
                  <button id={`item-candidate-${candidate.candidate_ref}`} type="button" onClick={() => {
                    setSelectedCandidateRef(candidate.candidate_ref);
                    setMobileDetailOpen(true);
                    requestAnimationFrame(() => {
                      const detail = document.getElementById(`item-candidate-detail-${candidate.candidate_ref}`);
                      if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                        detail.focus();
                      }
                    });
                  }} aria-current={selectedCandidate.candidate_ref === candidate.candidate_ref ? "true" : undefined} className={`min-h-11 w-full border-l-2 px-4 py-3 text-left transition-colors ${selectedCandidate.candidate_ref === candidate.candidate_ref ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}>
                    <span className="block text-sm font-semibold text-foreground [overflow-wrap:anywhere]">{candidate.name || t("preview.untitled")}</span>
                    <span className="mt-1 block truncate text-xs text-muted">{candidate.item_type || t("preview.untyped")} · {itemT(`status.${candidate.lifecycle_status}`)}</span>
                    {candidateFieldErrors[candidate.candidate_ref] && Object.keys(candidateFieldErrors[candidate.candidate_ref]).length > 0 && <span className="mt-2 block text-xs font-medium text-red-600 dark:text-red-300">{t("preview.hasErrors")}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <article id={`item-candidate-detail-${selectedCandidate.candidate_ref}`} className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-h-0 min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30`} tabIndex={0} aria-label={`${t("preview.detailLabel")} · ${selectedCandidate.name}`}>
            <div className="px-5 py-6 sm:px-7">
              <button type="button" className="mb-5 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
                const candidateRef = selectedCandidate.candidate_ref;
                setMobileDetailOpen(false);
                requestAnimationFrame(() => document.getElementById(`item-candidate-${candidateRef}`)?.focus());
              }}>← {t("actions.backToRoster")}</button>
              <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 flex-wrap items-center gap-1"><h3 className="min-w-0 text-xl font-semibold text-foreground [overflow-wrap:anywhere]">{selectedCandidate.name || t("preview.untitled")}</h3><SectionEditButton label={itemT("actions.edit")} isDisabled={readOnly} onPress={() => document.getElementById(`item-candidate-detail-${selectedCandidate.candidate_ref}`)?.querySelector<HTMLElement>("input, select, textarea")?.focus()} /></div>
                <Button variant="ghost" size="sm" className="text-danger" onPress={() => removeCandidate(selectedCandidate.candidate_ref)} isDisabled={readOnly}>{t("actions.removeCandidate")}</Button>
              </div>
              {candidateFieldErrors[selectedCandidate.candidate_ref] && Object.keys(candidateFieldErrors[selectedCandidate.candidate_ref]).length > 0 && <RelationEditorErrorSummary message={t("errors.validation")} fieldErrors={candidateFieldErrors[selectedCandidate.candidate_ref]} className="mt-6" />}
              <div className="pt-7">
                <ItemFieldsForm
                  value={selectedCandidate}
                  characters={characters}
                  factions={factions}
                  locations={locations}
                  disabled={readOnly}
                  fieldErrors={candidateFieldErrors[selectedCandidate.candidate_ref]}
                  errorIdPrefix={`item-candidate-${selectedCandidate.candidate_ref}`}
                  onChange={(fields) => updateCandidate(fields)}
                />
              </div>
            </div>
          </article>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 place-items-center px-5 py-12 text-center"><p className="text-sm font-medium text-foreground">{t("preview.emptyTitle")}</p></div>
      )}

      <footer className="shrink-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:px-6">
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
          <Button variant="ghost" size="sm" onPress={discardCandidate} isDisabled={candidateState.status === "confirming"}>{t("actions.discard")}</Button>
          <Button variant="primary" size="sm" onPress={() => void confirmCandidates()} isDisabled={readOnly || candidates.length === 0}>{candidateState.status === "confirming" ? t("actions.confirming") : t("actions.confirm")}</Button>
        </div>
      </footer>
    </section>
  );
}
