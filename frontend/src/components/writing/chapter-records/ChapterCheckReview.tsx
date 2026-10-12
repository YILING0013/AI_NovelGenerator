"use client";

import { Button, Modal } from "@heroui/react";
import { useContext, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPost } from "@/lib/api";
import type { ItemFactReadResultV1, ItemFactsAtPositionV1 } from "@/types/itemFacts";
import type { CharacterRelationResponseV1, CharacterResponseV1 } from "@/types/character";
import type { EntityChoices, HierarchyRecord } from "@/types/hierarchy";
import type { CharacterVolumeStateListV1, CharacterVolumeStateReadV1 } from "@/types/characterVolumeState";
import type { ChapterPsychologicalCheckSourceV1 } from "@/types/chapterRecords";
import { parseItemListV1, type ItemReadV1 } from "@/types/item";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import { createChapterCheckReview, readChapterCheckReviews, type ChapterCharacterRelationTarget, type ChapterCheckReviewMember, type ChapterRecordDraft } from "./chapterRecordDrafts";

/** 功能：为同一章修订建立两至五项检查，逐项回到原确认表单。Args: props 来源章、名称和继续入口。Returns: 本机检查清单及创建弹窗。 */
export default function ChapterCheckReview({ novelId, chapter, choices, selectedReviewId, disabled, opening = false, refreshToken, onResumeDraft, onNavigateItem, relationCheckVersion = 1, itemCheckVersion = 1 }: {
  novelId: string;
  chapter: HierarchyRecord;
  choices: EntityChoices;
  selectedReviewId?: string | null;
  disabled: boolean;
  opening?: boolean;
  refreshToken: string;
  relationCheckVersion?: 1 | 2;
  itemCheckVersion?: 1 | 2;
  onResumeDraft: (draft: ChapterRecordDraft) => void;
  onNavigateItem?: (itemId: string, chapterId: string, reviewId: string) => void;
}) {
  const t = useTranslations("writing.chapterRecords");
  const characterT = useTranslations("writing.characters");
  const active = useContext(RetainedViewActive);
  const [reviews, setReviews] = useState<Awaited<ReturnType<typeof readChapterCheckReviews>>>([]);
  const [loadedChapterId, setLoadedChapterId] = useState<string | null>(null);
  const [listError, setListError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [states, setStates] = useState<CharacterVolumeStateReadV1[]>([]);
  const [items, setItems] = useState<ItemReadV1[]>([]);
  const [itemFacts, setItemFacts] = useState<ItemFactsAtPositionV1[]>([]);
  const [readingItems, setReadingItems] = useState(false);
  const [itemReadError, setItemReadError] = useState("");
  const [relations, setRelations] = useState<CharacterRelationResponseV1[]>([]);
  const [characters, setCharacters] = useState<Pick<CharacterResponseV1, "novel_id" | "character_id" | "name" | "status" | "is_deleted">[]>([]);
  const [source, setSource] = useState<ChapterPsychologicalCheckSourceV1 | null>(null);
  const [kind, setKind] = useState<ChapterCheckReviewMember["kind"]>("psychological");
  const [targetId, setTargetId] = useState("");
  const [newHolderId, setNewHolderId] = useState("");
  const [targets, setTargets] = useState<ChapterRecordDraft[]>([]);
  const chapterId = chapter.chapter_id!;

  useEffect(() => {
    if (!active) return;
    let disposed = false;
    void readChapterCheckReviews(novelId, chapterId).then((rows) => {
      if (!disposed) { setReviews(rows); setListError(""); setLoadedChapterId(chapterId); }
    }).catch(() => { if (!disposed) setListError(t("localFailed")); });
    return () => { disposed = true; };
  }, [active, novelId, chapterId, refreshToken, refresh, t]);

  useEffect(() => {
    if (!active) return;
    const reload = () => setRefresh((value) => value + 1);
    window.addEventListener("focus", reload);
    return () => window.removeEventListener("focus", reload);
  }, [active]);

  useEffect(() => {
    if (!open || !active) return;
    const abort = new AbortController();
    setLoading(true); setError("");
    void Promise.all([
      apiGet<CharacterVolumeStateListV1>(`/api/character-volume-states/novel/${novelId}/volume/${chapter.volume_id}?status=active`, { signal: abort.signal }),
      apiGet<unknown>(`/api/items/novel/${novelId}`, { signal: abort.signal }),
      apiGet<{ data: CharacterResponseV1[] }>(`/api/characters/novel/${novelId}`, { signal: abort.signal }),
      apiGet<{ data: CharacterRelationResponseV1[] }>(`/api/character-relations/novel/${novelId}?is_active=true`, { signal: abort.signal }),
    ]).then(([page, itemRows, characterRows, relationRows]) => {
      if (abort.signal.aborted) return;
      setStates(page.data.filter((state) => !state.is_deleted && state.novel_id === novelId && state.volume_id === chapter.volume_id));
      setItems(parseItemListV1(itemRows, novelId));
      setCharacters(characterRows.data.filter((row) => row.novel_id === novelId && !row.is_deleted && row.status === "active"));
      setRelations(relationRows.data.filter((row) => row.novel_id === novelId && !row.is_deleted && row.is_active));
    }).catch((failure) => { if (!abort.signal.aborted) setError((failure as Error).message); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [open, active, novelId, chapter.volume_id]);

  useEffect(() => {
    setItemFacts([]); setItemReadError(""); setReadingItems(false);
    if (!open || !active || itemCheckVersion !== 2 || !source) return;
    const abort = new AbortController(); setReadingItems(true);
    void (async () => {
      const rows: ItemFactsAtPositionV1[] = [];
      for (let offset = 0; offset < items.length; offset += 200) {
        const page = await apiPost<ItemFactReadResultV1>(`/api/item-facts/novel/${novelId}/read`, { item_ids: items.slice(offset, offset + 200).map((item) => item.item_id), position: { version: 1, intent: "chapter_before", target_type: "chapter", target_id: source.chapter_id } }, { signal: abort.signal });
        if (page.novel_id !== novelId) throw new Error(t("itemOwner.wrongScope"));
        rows.push(...page.items);
      }
      if (!abort.signal.aborted) setItemFacts(rows);
    })().catch((failure) => { if (!abort.signal.aborted) setItemReadError(failure.message); }).finally(() => { if (!abort.signal.aborted) setReadingItems(false); });
    return () => abort.abort();
  }, [open, active, itemCheckVersion, source, items, novelId, t]);

  const availableStates = states.filter((row) => !targets.some((draft) => draft.targetState?.state_id === row.state_id));
  const state = availableStates.find((row) => row.state_id === targetId);
  const positionedItems = itemCheckVersion === 2 ? items.flatMap((row) => {
    const fact = itemFacts.find((entry) => entry.item_id === row.item_id);
    return fact?.values ? [{ ...row, ...fact.values, version: fact.version }] : [];
  }) : items;
  const eligibleItems = positionedItems.filter((row) => !row.is_deleted && row.lifecycle_status === "held" && characters.some((entry) => entry.character_id === row.owner_character_id));
  const availableItems = eligibleItems.filter((row) => !targets.some((draft) => draft.itemOwner?.item_id === row.item_id));
  const item = availableItems.find((row) => row.item_id === targetId);
  const availableRelations = relations.filter((row) => !targets.some((draft) => draft.relationTarget?.relation_id === row.relation_id));
  const relation = availableRelations.find((row) => row.relation_id === targetId);
  const newHolder = characters.find((row) => row.character_id === newHolderId && row.character_id !== item?.owner_character_id);
  const name = (characterId: string) => characters.find((row) => row.character_id === characterId)?.name ?? choices.character_ids.find((row) => row.id === characterId)?.name ?? characterId;
  const relationName = (target: Omit<ChapterCharacterRelationTarget, "version" | "current_state">) => `${target.source_character_name ?? name(target.source_character_id)} / ${target.target_character_name ?? name(target.target_character_id)} · ${characterT(`options.relationType.${target.relation_type}`)}`;
  const canAdd = targets.length < 5 && (kind === "psychological" ? Boolean(state) : kind === "itemOwner" ? Boolean(item && newHolder) : Boolean(relation));

  return <section data-testid="chapter-check-reviews" aria-label={t("review.title")} className="grid min-w-0 gap-3 border-y border-border py-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{t("review.title")}</h3><Button size="sm" variant="outline" isDisabled={disabled || opening} onPress={() => {
      setSource(null); setKind("psychological"); setTargetId(""); setNewHolderId(""); setTargets([]); setStates([]); setItems([]); setRelations([]); setCharacters([]); setError(""); setOpen(true);
    }}>{t("review.create")}</Button></div>
    {listError && <RelationEditorErrorSummary message={listError} />}
    {selectedReviewId && loadedChapterId === chapterId && !listError && !reviews.some(({ review }) => review.reviewId === selectedReviewId) && <p role="status" className="text-sm text-muted">{t("review.notFound")}</p>}
    <ul className="divide-y divide-border">{reviews.map(({ review, members }) => <li key={review.reviewId} data-testid="chapter-check-review" data-review-id={review.reviewId} aria-current={review.reviewId === selectedReviewId ? "true" : undefined} className={`grid min-w-0 gap-2 py-3 ${review.reviewId === selectedReviewId ? "border-l-2 border-accent pl-3" : ""}`}>
      <p className="text-xs text-muted">{t("review.sourceVersion", { version: review.source.version })}</p>
      <ul className="grid gap-2">{Object.entries(review.members).map(([memberId, member]) => {
        const entry = members[memberId];
        const draft = entry.draft;
        const check = member.kind === "psychological" ? draft?.check : member.kind === "itemOwner" ? draft?.itemOwnerCheck : draft?.relationCheck;
        const fact = entry.itemFact ?? entry.relationFact;
        const status = fact?.operation?.saved || fact?.draft?.command?.saved || entry.operation?.saved || draft?.command?.saved ? "saved"
          : fact?.draft?.command || fact?.operation ? (fact.draft?.command ?? fact.operation)!.unknown === false ? "failed" : "unknown"
          : fact?.draft ? "confirm" : fact && "preparation" in fact && fact.preparation ? "preparation" : !draft ? "missing"
          : draft.command ? draft.command.unknown === false ? "failed" : "unknown"
          : check?.status === "failed" ? "checkFailed" : check?.status === "rejected" ? "rejected"
          : check?.status === "running" || check?.status === "interrupted" ? "interrupted"
          : check?.status === "adopted" ? "confirm" : check?.result?.candidate.suggestion === null ? "noSuggestion" : check ? "pending"
          : member.kind === "psychological" && draft.evidence ? "confirm" : "notStarted";
        return <li key={memberId} data-testid={`chapter-check-review-${member.kind}`} data-member-id={memberId} className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <span className="min-w-0 break-words text-sm">{member.kind === "psychological" ? `${member.target.name} · ${t("psychologicalState")}` : member.kind === "itemOwner" ? `${member.target.name} · ${member.target.from_name} → ${member.target.to_name}` : relationName(member.target)}</span>
          <div className="flex flex-wrap items-center gap-2"><span data-review-status={status} className="text-xs text-muted">{t(`review.status.${status}`)}</span>{draft && <Button size="sm" variant="outline" isDisabled={disabled || member.kind === "itemOwner" && (opening || !onNavigateItem)} aria-disabled={opening || undefined} onPress={() => {
            if (opening) return;
            if (member.kind === "itemOwner") onNavigateItem?.(member.target.item_id, chapterId, review.reviewId);
            else onResumeDraft(draft);
          }}>{t(member.kind === "psychological" ? "review.continuePsychological" : member.kind === "itemOwner" ? "review.continueItem" : "review.continueRelation")}</Button>}</div>
        </li>;
      })}</ul>
    </li>)}</ul>
    <RetainedModalBackdrop isOpen={open} isDismissable={!saving} isKeyboardDismissDisabled={saving} onOpenChange={(next) => { if (!saving) setOpen(next); }}>
      <Modal.Container scroll="inside"><Modal.Dialog className="h-[100dvh] w-full max-w-none p-0 sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
        <Modal.Header className="flex shrink-0 items-center justify-between gap-3 px-5 py-4 sm:px-7"><Modal.Heading>{t("review.create")}</Modal.Heading><Modal.CloseTrigger isDisabled={saving} /></Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 overflow-y-auto px-5 py-5 sm:px-7"><div data-testid="chapter-check-review-create" className="grid min-w-0 gap-4">
          {error && <RelationEditorErrorSummary message={error} />}{loading && <p role="status">{t("loading")}</p>}
          <EvidencePicker novelId={novelId} chapters={[chapter]} value={null} disabled={saving} onSelectRevision={(next) => {
            if (source && (!next || source.revision_id !== next.revision_id || source.content_hash !== next.content_hash)) { setTargets([]); setTargetId(""); setNewHolderId(""); }
            setSource(next);
          }} label={t("source")} />
          {kind === "itemOwner" && (readingItems || itemReadError) && <p role={itemReadError ? "alert" : "status"} className="text-sm text-muted">{itemReadError || t("loading")}</p>}
          <div className="grid min-w-0 gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-xs text-muted">{t("review.targetKind")}<select className={INPUT} value={kind} disabled={loading || saving} onChange={(event) => { setKind(event.target.value as ChapterCheckReviewMember["kind"]); setTargetId(""); setNewHolderId(""); }}>
              <option value="psychological">{t("psychologicalState")}</option><option value="itemOwner">{t("itemOwner.holder")}</option><option value="characterRelation">{t("relationState.currentState")}</option>
            </select></label>
            {kind === "psychological" && <label className="grid gap-1 text-xs text-muted">{t("character")}<select className={INPUT} value={targetId} disabled={loading || saving} onChange={(event) => setTargetId(event.target.value)}><option value="">{t("chooseCharacter")}</option>{availableStates.map((row) => <option key={row.state_id} value={row.state_id}>{name(row.character_id)}</option>)}</select></label>}
            {kind === "itemOwner" && <><label className="grid gap-1 text-xs text-muted">{t("itemOwner.item")}<select className={INPUT} value={targetId} disabled={loading || saving} onChange={(event) => { setTargetId(event.target.value); setNewHolderId(""); }}><option value="">{t("review.chooseItem")}</option>{availableItems.map((row) => <option key={row.item_id} value={row.item_id}>{row.name} · {name(row.owner_character_id!)}</option>)}</select></label>
              <label className="grid gap-1 text-xs text-muted">{t("itemOwner.newHolder")}<select className={INPUT} value={newHolderId} disabled={!item || loading || saving} onChange={(event) => setNewHolderId(event.target.value)}><option value="">{t("chooseCharacter")}</option>{characters.filter((row) => row.character_id !== item?.owner_character_id).map((row) => <option key={row.character_id} value={row.character_id}>{name(row.character_id)}</option>)}</select></label></>}
            {kind === "characterRelation" && <label className="grid gap-1 text-xs text-muted">{t("relationState.relation")}<select className={INPUT} value={targetId} disabled={loading || saving} onChange={(event) => setTargetId(event.target.value)}><option value="">{t("relationState.chooseRelation")}</option>{availableRelations.map((row) => <option key={row.relation_id} value={row.relation_id}>{relationName(row)}</option>)}</select></label>}
          </div>
          {!loading && !error && !(kind === "psychological" ? availableStates.length : kind === "itemOwner" ? availableItems.length : availableRelations.length) && <p role="status" className="text-sm text-muted">{t("review.noTargets")}</p>}
          <div><Button variant="outline" isDisabled={loading || saving || !canAdd} onPress={() => {
            if (!canAdd) return;
            const common = { key: crypto.randomUUID(), revision: 1, chapterId, title: "", content: "", summary: "", issues: [], psychologicalState: "", reason: "", evidence: null, relatedEntities: [], targetState: null, expectedReportVersion: 0, recordId: null };
            let draft: ChapterRecordDraft;
            if (kind === "psychological" && state) draft = { ...common, mode: "psychological-state", psychologicalState: state.psychological_state, targetState: { state_id: state.state_id, version: state.version, character_id: state.character_id, volume_id: state.volume_id, psychological_state: state.psychological_state, name: name(state.character_id) } };
            else if (kind === "itemOwner" && item && newHolder) draft = { ...common, mode: "item-owner", itemCheckVersion, title: item.name, itemOwner: { item_id: item.item_id, name: item.name, version: item.version, from_character_id: item.owner_character_id!, from_name: name(item.owner_character_id!), to_character_id: newHolder.character_id, to_name: name(newHolder.character_id) } };
            else if (kind === "characterRelation" && relation) {
              const { relation_id, version, source_character_id, target_character_id, source_character_name, target_character_name, relation_type, current_state } = relation;
              draft = { ...common, mode: "character-relation-state", relationCheckVersion, relationState: relationCheckVersion === 2 ? "" : current_state, relationTarget: { relation_id, version, source_character_id, target_character_id, source_character_name, target_character_name, relation_type, current_state } };
            } else return;
            setTargets([...targets, draft]); setTargetId(""); setNewHolderId("");
          }}>{t("review.addTarget")}</Button></div>
          <div><h4 className="text-sm font-semibold">{t("review.selectedTargets", { count: targets.length })}</h4><ul className="divide-y divide-border">{targets.map((draft) => {
            const label = draft.targetState ? `${draft.targetState.name} · ${t("psychologicalState")}` : draft.itemOwner ? `${draft.itemOwner.name} · ${draft.itemOwner.from_name} → ${draft.itemOwner.to_name}` : relationName(draft.relationTarget!);
            return <li key={draft.key} data-testid="chapter-check-selected-target" className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-2"><span className="min-w-0 break-words text-sm">{label}</span><Button size="sm" variant="ghost" isDisabled={saving} aria-label={t("review.removeTarget", { name: label })} onPress={() => setTargets(targets.filter((entry) => entry.key !== draft.key))}>{t("review.remove")}</Button></li>;
          })}</ul></div>
        </div></Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex shrink-0 flex-wrap gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7"><Button variant="primary" isDisabled={saving || loading || !source || targets.length < 2 || targets.length > 5} onPress={async () => {
          if (!source || targets.length < 2 || targets.length > 5 || saving) return;
          setSaving(true); setError("");
          try { await createChapterCheckReview(novelId, source, targets); setOpen(false); setRefresh((value) => value + 1); }
          catch { setError(t("localFailed")); }
          finally { setSaving(false); }
        }}>{t(saving ? "saving" : "review.createConfirm")}</Button><Button variant="ghost" isDisabled={saving} onPress={() => setOpen(false)}>{t("review.cancel")}</Button></Modal.Footer>
      </Modal.Dialog></Modal.Container>
    </RetainedModalBackdrop>
  </section>;
}
