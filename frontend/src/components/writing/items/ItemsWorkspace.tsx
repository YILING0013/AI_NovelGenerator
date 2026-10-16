"use client";
import { useAssistantRefresh, useAssistantResource } from "@/components/writing/assistant/AssistantContext";
import { RetainedModalBackdrop, RetainedViewActive, RetainedViews } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import {
  ConfirmActionModal,
  RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import ItemFieldsForm, { type ItemEditorSection } from "@/components/writing/items/ItemFieldsForm";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import TagList from "@/components/shared/TagList";
import ItemCandidateWorkspace from "@/components/writing/items/ItemCandidateWorkspace";
import ItemFactsPanel from "./ItemFactsPanel";
import ItemFactPreparationDialog from "./ItemFactPreparationDialog";
import ItemFactConfirmationDialog from "./ItemFactConfirmationDialog";
import { readItemFactPreparations, discardItemFactPreparation, writeItemFactPreparation, type ItemFactPreparationV1 } from "./itemFactPreparation";
import type { ItemFactDraftV1, ItemFactBatchDraftV1 } from "./itemFactDrafts";
import { readFactDrafts, writeFactDraft } from "../characters/factDraftStorage";
import DraftChip from "@/components/shared/DraftChip";
import { loadCharacterFactChapters } from "../characters/characterFactPositions";
import type { ItemFactsAtPositionV1, ItemFactReadResultV1 } from "@/types/itemFacts";
import type { HierarchyRecord } from "@/types/hierarchy";
import ItemOwnerConfirmation, { ItemOwnerConfirmationEntry } from "@/components/writing/items/ItemOwnerConfirmation";
import { readChapterCheckReviews, type ChapterCheckReviewRead, type ChapterRecordDraft } from "@/components/writing/chapter-records/chapterRecordDrafts";
import {
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
  ApiRequestError,
  type ApiFieldErrors,
} from "@/lib/api";
import type { CharacterResponseV1 } from "@/types/character";
import { formatStableReferenceLabel, isBusinessId } from "@/types/contracts";
import {
  parseActiveItemListV1,
  parseItemDeleteImpactV1,
  parseItemHardDeleteResponseV1,
  parseItemReadV1,
  parseTrashItemListV1,
  type ItemDeleteImpactV1,
  type ItemFieldsV1,
  type ItemLifecycleStatus,
  type ItemReadV1,
  type ItemUpdateV1,
} from "@/types/item";
import { parseActiveLocationListV1, type LocationReadV1 } from "@/types/location";
import type { CoreFaction } from "@/types/novel";

export type ItemsWorkspaceView = "items" | "trash";

export interface ItemWorkspaceFilters {
  q: string;
  itemType: string;
  status: "all" | ItemLifecycleStatus;
  ownerId: string;
  factionId: string;
  locationId: string;
}

interface ItemsWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  initialView?: ItemsWorkspaceView;
  requestedItemId?: string | null;
  chapterId?: string | null;
  chapterReviewId?: string | null;
  onNavigateChapter?: (chapterId: string, reviewId: string) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  initialFilters?: Partial<ItemWorkspaceFilters>;
  onItemChange?: (
    view: ItemsWorkspaceView,
    itemId: string | null,
    filters: ItemWorkspaceFilters,
    replace?: boolean,
  ) => void;
  onFormalFactsChanged?: () => void;
}

interface ItemInlineSession {
  section: ItemEditorSection;
  source: ItemReadV1;
  draft: ItemFieldsV1;
  error: string;
  fieldErrors: ApiFieldErrors;
}

const SECTION_FIELDS: Record<ItemEditorSection, (keyof ItemFieldsV1)[]> = {
  identity: ["name", "aliases", "item_type", "description"],
  profile: ["appearance", "origin"],
  capabilities: ["abilities", "limitations", "costs"],
  references: ["owner_character_id", "controlling_faction_id", "current_location_id"],
  story: ["story_function", "tags"],
};

type ConfirmIntent =
  | { kind: "soft-delete"; item: ItemReadV1 }
  | { kind: "restore"; item: ItemReadV1 }
  | { kind: "hard-delete"; item: ItemReadV1 };

interface ReferenceErrors {
  character: string;
  faction: string;
  location: string;
}

type ItemCharacterReference = Pick<
  CharacterResponseV1,
  "novel_id" | "character_id" | "name" | "status" | "is_deleted"
>;
type ItemFactionReference = Required<Pick<
  CoreFaction,
  "novel_id" | "faction_id" | "name" | "active_status" | "is_deleted"
>>;

const FILTER_CLASS =
  "min-h-10 min-w-0 w-full rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15";
const TAB_PREFIX = "items-workspace";
const ITEM_STATUSES: ItemLifecycleStatus[] = ["available", "held", "lost", "destroyed", "consumed"];
const TERMINAL_ITEM_STATUSES = new Set<ItemLifecycleStatus>(["destroyed", "consumed"]);
const EMPTY_ITEMS: ItemReadV1[] = [];
const EMPTY_CHARACTERS: ItemCharacterReference[] = [];
const EMPTY_FACTIONS: ItemFactionReference[] = [];
const EMPTY_LOCATIONS: LocationReadV1[] = [];
const DEFAULT_FILTERS: ItemWorkspaceFilters = {
  q: "",
  itemType: "all",
  status: "all",
  ownerId: "all",
  factionId: "all",
  locationId: "all",
};
const EMPTY_ITEM: ItemFieldsV1 = {
  name: "",
  aliases: [],
  item_type: "",
  description: "",
  appearance: "",
  origin: "",
  abilities: [],
  limitations: [],
  costs: [],
  owner_character_id: null,
  controlling_faction_id: null,
  current_location_id: null,
  lifecycle_status: "available",
  story_function: "",
  tags: [],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseCharacterReferences(value: unknown, novelId: string): ItemCharacterReference[] {
  if (!isRecord(value) || !Array.isArray(value.data)) throw new Error("Invalid character reference response");
  const ids = new Set<string>();
  return value.data.map((entry) => {
    if (
      !isRecord(entry)
      || entry.novel_id !== novelId
      || !isBusinessId("character", entry.character_id)
      || typeof entry.name !== "string"
      || entry.name.trim().length === 0
      || (entry.status !== "active" && entry.status !== "inactive")
      || typeof entry.is_deleted !== "boolean"
      || ids.has(entry.character_id)
    ) throw new Error("Invalid character reference response");
    ids.add(entry.character_id);
    return {
      novel_id: entry.novel_id,
      character_id: entry.character_id,
      name: entry.name,
      status: entry.status,
      is_deleted: entry.is_deleted,
    };
  });
}

function parseFactionReferences(value: unknown, novelId: string): ItemFactionReference[] {
  if (!isRecord(value) || !Array.isArray(value.data)) throw new Error("Invalid faction reference response");
  const ids = new Set<string>();
  return value.data.map((entry) => {
    if (
      !isRecord(entry)
      || entry.novel_id !== novelId
      || !isBusinessId("faction", entry.faction_id)
      || typeof entry.name !== "string"
      || entry.name.trim().length === 0
      || (entry.active_status !== "active" && entry.active_status !== "inactive")
      || typeof entry.is_deleted !== "boolean"
      || ids.has(entry.faction_id)
    ) throw new Error("Invalid faction reference response");
    ids.add(entry.faction_id);
    return {
      novel_id: entry.novel_id,
      faction_id: entry.faction_id,
      name: entry.name,
      active_status: entry.active_status,
      is_deleted: entry.is_deleted,
    };
  });
}

/**
 * 显示物品列表、详情、编辑和回收站。
 *
 * Args:
 *   mode: 当前是新建小说还是编辑小说。
 *   novelId: 已保存小说的 ID。
 *   initialView: 默认显示物品列表还是回收站。
 *   requestedItemId: 地址中指定的物品 ID。
 *   chapterId、chapterReviewId: 只定位本机关联稿，不自动打开确认层。
 *   onNavigateChapter: 经上层保稿后返回关联稿所属章节。
 *   onDirtyChange、onBusyChange: 将持有人确认的草稿和保存状态交给导航守卫。
 *   beforeLeaveRef: 离开前取消检查并等待当前稿件保存。
 *   initialFilters: 地址中保存的筛选条件。
 *   onItemChange: 选择物品、筛选或切换页面时更新地址。
 *   onFormalFactsChanged: 物品保存成功后通知上层刷新数据。
 *
 * Returns:
 *   物品管理页面。
 */
export default function ItemsWorkspace({
  mode,
  novelId,
  initialView = "items",
  requestedItemId = null,
  chapterId = null,
  chapterReviewId = null,
  onNavigateChapter,
  onDirtyChange,
  onBusyChange,
  beforeLeaveRef,
  initialFilters,
  onItemChange,
  onFormalFactsChanged,
}: ItemsWorkspaceProps) {
  const t = useTranslations("writing.items");
  const f = useTranslations("writing.itemFacts");
  const tRecords = useTranslations("writing.chapterRecords");
  const tLayout = useTranslations("writing.listLayout");
  const active = useContext(RetainedViewActive);
  const [inlineSessions, setInlineSessions] = useState<Record<string, ItemInlineSession | undefined>>({});
  const [listCollapsed, setListCollapsed] = useState(false);
  const [wideLayout, setWideLayout] = useState(false);
  const workspaceRef = useRef<HTMLElement>(null);
  const [view, setView] = useState<ItemsWorkspaceView>(initialView);
  const [filters, setFilters] = useState<ItemWorkspaceFilters>({ ...DEFAULT_FILTERS, ...initialFilters });
  const [storedItems, setItems] = useState<ItemReadV1[]>([]);
  const [storedTrash, setTrash] = useState<ItemReadV1[]>([]);
  const [storedCharacters, setCharacters] = useState<ItemCharacterReference[]>([]);
  const [storedFactions, setFactions] = useState<ItemFactionReference[]>([]);
  const [storedLocations, setLocations] = useState<LocationReadV1[]>([]);
  const [referenceErrors, setReferenceErrors] = useState<ReferenceErrors>({ character: "", faction: "", location: "" });
  const [loadedNovelId, setLoadedNovelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState("");
  const [pageActionError, setPageActionError] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [invalidRequestedId, setInvalidRequestedId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmIntent, setConfirmIntent] = useState<ConfirmIntent | null>(null);
  const [impact, setImpact] = useState<ItemDeleteImpactV1 | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [actionItemId, setActionItemId] = useState("");
  const [hasCandidate, setCandidateReviewing] = useState(false);
  const candidateReviewing = view === "items" && hasCandidate;
  const [candidateBusy, setCandidateBusy] = useState(false);
  const [ownerBusy, setOwnerBusy] = useState(false);
  const [ownerDirty, setOwnerDirty] = useState(false);
  const [latestFacts, setLatestFacts] = useState<Record<string, ItemFactsAtPositionV1>>({});
  const [factReadRefresh, setFactReadRefresh] = useState(0);
  const [factBusy, setFactBusy] = useState(false);
  const [factChapters, setFactChapters] = useState<HierarchyRecord[] | null>(null);
  const [factPreparation, setFactPreparation] = useState<ItemFactPreparationV1 | null>(null);
  const [closedPreparation, setClosedPreparation] = useState<ItemFactPreparationV1 | null>(null);
  const preparationDialog = factPreparation ?? closedPreparation;
  const [factDraft, setFactDraft] = useState<ItemFactDraftV1 | ItemFactBatchDraftV1 | null>(null);
  const [factPreparations, setFactPreparations] = useState<ItemFactPreparationV1[]>([]);
  const [factDrafts, setFactDrafts] = useState<Array<ItemFactDraftV1 | ItemFactBatchDraftV1>>([]);
  const [factRefresh, setFactRefresh] = useState(0);
  const factBeforeLeave = useRef<(() => Promise<void>) | null>(null);
  const ownerBeforeLeave = useRef<(() => Promise<void>) | null>(null);
  const [ownerSession, setOwnerSession] = useState<{ novelId: string; itemId: string; item: ItemReadV1 | null; draft?: ChapterRecordDraft; entryVersion: number; closed: boolean } | null>(null);
  const [ownerEntryVersion, setOwnerEntryVersion] = useState(0);
  const [ownerSaved, setOwnerSaved] = useState(false);
  const [reviewEntry, setReviewEntry] = useState<{ key: string; value: ChapterCheckReviewRead | null; memberId: string | null; error: string } | null>(null);
  const reviewKey = novelId && chapterId && chapterReviewId && requestedItemId && view === "items" ? `${novelId}:${chapterId}:${chapterReviewId}:${requestedItemId}` : null;
  const currentReview = reviewEntry?.key === reviewKey ? reviewEntry : null;
  const currentReviewMember = currentReview?.value && currentReview.memberId ? currentReview.value.members[currentReview.memberId] : null;
  const [candidateSessionKey, setCandidateSessionKey] = useState(0);
  const loadAbortRef = useRef<AbortController | null>(null);
  const loadRequestIdRef = useRef(0);
  const commandAbortRef = useRef<AbortController | null>(null);
  const commandRequestIdRef = useRef(0);
  const currentNovelIdRef = useRef(novelId);
  const previousNovelIdRef = useRef(novelId);
  const previousRequestedIdRef = useRef(requestedItemId);
  // 消费键包含视图与筛选；本地选择不能改写它，否则父级回放新 URL 前，旧深链会覆盖刚选择的物品。
  const appliedRequestedKeyRef = useRef<string | null>(null);
  currentNovelIdRef.current = novelId;

  const initialQ = initialFilters?.q ?? DEFAULT_FILTERS.q;
  const initialItemType = initialFilters?.itemType ?? DEFAULT_FILTERS.itemType;
  const initialStatus = initialFilters?.status ?? DEFAULT_FILTERS.status;
  const initialOwnerId = initialFilters?.ownerId ?? DEFAULT_FILTERS.ownerId;
  const initialFactionId = initialFilters?.factionId ?? DEFAULT_FILTERS.factionId;
  const initialLocationId = initialFilters?.locationId ?? DEFAULT_FILTERS.locationId;
  const workspaceReady = loadedNovelId === novelId;
  const items = workspaceReady ? storedItems : EMPTY_ITEMS;
  const trash = workspaceReady ? storedTrash : EMPTY_ITEMS;
  const characters = workspaceReady ? storedCharacters : EMPTY_CHARACTERS;
  const factions = workspaceReady ? storedFactions : EMPTY_FACTIONS;
  const locations = workspaceReady ? storedLocations : EMPTY_LOCATIONS;
  const sourceItems = view === "items" ? items : trash;
  const canUseSavedNovel = mode === "edit" && Boolean(novelId);
  const busy = loading || saving || impactLoading || Boolean(actionItemId) || candidateBusy || ownerBusy || factBusy;

  const startFact = async (preparation: ItemFactPreparationV1) => {
    await writeItemFactPreparation(preparation, null);
    setFactPreparation(preparation);
  };
  useEffect(() => {
    if (!active || !novelId) return;
    const abort = new AbortController();
    void loadCharacterFactChapters(novelId, abort.signal).then((chapters) => { if (!abort.signal.aborted) setFactChapters(chapters); }).catch((failure) => { if (!abort.signal.aborted) setPageActionError(failure.message); });
    const load = () => {
      void Promise.all([readItemFactPreparations(novelId), readFactDrafts<ItemFactDraftV1>("item", `${novelId}:item-facts`), readFactDrafts<ItemFactBatchDraftV1>("item_batch", `${novelId}:item-fact-batches`)]).then(([preparations, singles, batches]) => {
        if (!abort.signal.aborted) { setFactPreparations(preparations); setFactDrafts([...singles, ...batches]); }
      }).catch((failure) => { if (!abort.signal.aborted) setPageActionError(failure.message); });
    };
    load(); window.addEventListener("focus", load);
    return () => { abort.abort(); window.removeEventListener("focus", load); };
  }, [active, novelId, factRefresh]);

  useEffect(() => {
    if (!active || !reviewKey || !novelId || !chapterId) return;
    let disposed = false;
    let readVersion = 0;
    // 只读取关联位置；认领和打开确认层必须等作者点击继续。
    const load = () => {
      const request = ++readVersion;
      void readChapterCheckReviews(novelId, chapterId).then((entries) => {
        if (disposed || request !== readVersion) return;
        const review = entries.find((entry) => entry.review.reviewId === chapterReviewId && entry.review.source.chapter_id === chapterId);
        const matches = review ? Object.entries(review.review.members).filter(([, member]) => member.kind === "itemOwner" && member.target.item_id === requestedItemId) : [];
        const memberId = matches.length === 1 ? matches[0][0] : null;
        const value = memberId ? review! : null;
        setReviewEntry({ key: reviewKey, value, memberId, error: value ? "" : tRecords("review.notFound") });
      }).catch(() => { if (!disposed && request === readVersion) setReviewEntry({ key: reviewKey, value: null, memberId: null, error: tRecords("localFailed") }); });
    };
    load();
    const focus = () => { if (document.visibilityState === "visible") load(); };
    window.addEventListener("focus", focus);
    return () => { disposed = true; window.removeEventListener("focus", focus); };
  }, [active, reviewKey, novelId, chapterId, chapterReviewId, requestedItemId, ownerEntryVersion, tRecords]);

  useEffect(() => {
    if (active) onDirtyChange?.(ownerDirty || Boolean(factPreparation || factDraft));
    return () => onDirtyChange?.(false);
  }, [active, ownerDirty, factPreparation, factDraft, onDirtyChange]);
  useEffect(() => {
    if (active) onBusyChange?.(ownerBusy || factBusy);
    return () => onBusyChange?.(false);
  }, [active, ownerBusy, factBusy, onBusyChange]);
  useEffect(() => {
    if (!active || !beforeLeaveRef) return;
    const leave = async () => { await ownerBeforeLeave.current?.(); await factBeforeLeave.current?.(); };
    beforeLeaveRef.current = leave;
    return () => { if (beforeLeaveRef.current === leave) beforeLeaveRef.current = null; };
  }, [active, beforeLeaveRef]);

  useEffect(() => {
    const element = workspaceRef.current?.querySelector<HTMLElement>(`#${TAB_PREFIX}-${view}-panel`);
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setWideLayout(entry.contentRect.width >= 800);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [view, canUseSavedNovel, novelId]);
  const hideList = listCollapsed && wideLayout;

  const loadWorkspace = useCallback(async (strict = false) => {
    if (!novelId || mode !== "edit") return;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestId = loadRequestIdRef.current + 1;
    const requestNovelId = novelId;
    loadAbortRef.current = controller;
    loadRequestIdRef.current = requestId;
    setLoading(true);
    setDataError("");
    try {
      const [activeResult, trashResult, characterResult, factionResult, locationResult] = await Promise.allSettled([
        apiGet<unknown>(`/api/items/novel/${novelId}`, { signal: controller.signal }),
        apiGet<unknown>(`/api/items/novel/${novelId}/trash`, { signal: controller.signal }),
        apiGet<unknown>(`/api/characters/novel/${novelId}`, { signal: controller.signal }),
        apiGet<unknown>(`/api/factions/novel/${novelId}`, { signal: controller.signal }),
        apiGet<unknown>(`/api/locations/novel/${novelId}`, { signal: controller.signal }),
      ]);
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
      ) { if (strict) throw new Error(f("readInterrupted")); return; }
      if (activeResult.status === "rejected") throw activeResult.reason;
      if (trashResult.status === "rejected") throw trashResult.reason;
      const nextItems = parseActiveItemListV1(activeResult.value, requestNovelId);
      const nextTrash = parseTrashItemListV1(trashResult.value, requestNovelId);
      const factRows: ItemFactsAtPositionV1[] = [];
      for (let offset = 0; offset < nextItems.length; offset += 200) {
        const result = await apiPost<ItemFactReadResultV1>(`/api/item-facts/novel/${novelId}/read`, { item_ids: nextItems.slice(offset, offset + 200).map((row) => row.item_id) }, { signal: controller.signal });
        if (result.novel_id !== requestNovelId) throw new Error(f("wrongScope"));
        factRows.push(...result.items);
      }
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) { if (strict) throw new Error(f("readInterrupted")); return; }
      setLatestFacts(Object.fromEntries(factRows.map((row) => [row.item_id, row])));
      setItems(nextItems);
      setTrash(nextTrash);
      setLoadedNovelId(requestNovelId);

      const nextReferenceErrors: ReferenceErrors = { character: "", faction: "", location: "" };
      if (characterResult.status === "fulfilled") {
        try {
          setCharacters(parseCharacterReferences(characterResult.value, requestNovelId));
        } catch {
          setCharacters([]);
          nextReferenceErrors.character = t("references.loadCharactersFailed");
        }
      } else {
        setCharacters([]);
        nextReferenceErrors.character = t("references.loadCharactersFailed");
      }
      if (factionResult.status === "fulfilled") {
        try {
          setFactions(parseFactionReferences(factionResult.value, requestNovelId));
        } catch {
          setFactions([]);
          nextReferenceErrors.faction = t("references.loadFactionsFailed");
        }
      } else {
        setFactions([]);
        nextReferenceErrors.faction = t("references.loadFactionsFailed");
      }
      if (locationResult.status === "fulfilled") {
        try {
          setLocations(parseActiveLocationListV1(locationResult.value, requestNovelId));
        } catch {
          setLocations([]);
          nextReferenceErrors.location = t("references.loadLocationsFailed");
        }
      } else {
        setLocations([]);
        nextReferenceErrors.location = t("references.loadLocationsFailed");
      }
      setReferenceErrors(nextReferenceErrors);
    } catch (error) {
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
      ) { if (strict) throw error; return; }
      setDataError(error instanceof ApiRequestError ? error.message : t("errors.load"));
      if (strict) throw error;
    } finally {
      if (
        !controller.signal.aborted
        && loadAbortRef.current === controller
        && loadRequestIdRef.current === requestId
        && currentNovelIdRef.current === requestNovelId
      ) setLoading(false);
    }
  }, [mode, novelId, t, f]);

  useAssistantRefresh(novelId, loadWorkspace);

  useEffect(() => {
    const novelChanged = previousNovelIdRef.current !== novelId;
    previousNovelIdRef.current = novelId;
    if (novelChanged) {
      setFactPreparation(null); setFactDraft(null); setFactPreparations([]); setFactDrafts([]); setLatestFacts({});
      setOwnerSession(null); setOwnerSaved(false); setOwnerDirty(false); setOwnerBusy(false); setReviewEntry(null);
      loadAbortRef.current?.abort();
      loadRequestIdRef.current += 1;
      commandAbortRef.current?.abort();
      commandRequestIdRef.current += 1;
      setLoadedNovelId(null);
      setItems([]);
      setTrash([]);
      setCharacters([]);
      setFactions([]);
      setLocations([]);
      setReferenceErrors({ character: "", faction: "", location: "" });
      setSelectedItemId("");
      appliedRequestedKeyRef.current = null;
      setInvalidRequestedId("");
      setMobileDetailOpen(false);
      setInlineSessions({});
      setConfirmIntent(null);
      setSaving(false);
      setImpactLoading(false);
      setActionItemId("");
      setCandidateReviewing(false);
      setCandidateBusy(false);
      setCandidateSessionKey((current) => current + 1);
      setPageActionError("");
    }
    void loadWorkspace();
    return () => loadAbortRef.current?.abort();
  }, [loadWorkspace, novelId]);

  useEffect(() => () => {
    commandAbortRef.current?.abort();
    commandRequestIdRef.current += 1;
  }, []);

  useEffect(() => {
    setView(initialView);
    setMobileDetailOpen(false);
    setConfirmIntent(null);
  }, [initialView]);

  useEffect(() => {
    const next: ItemWorkspaceFilters = {
      q: initialQ,
      itemType: initialItemType,
      status: initialStatus,
      ownerId: initialOwnerId,
      factionId: initialFactionId,
      locationId: initialLocationId,
    };
    setFilters((current) => (
      current.q === next.q
      && current.itemType === next.itemType
      && current.status === next.status
      && current.ownerId === next.ownerId
      && current.factionId === next.factionId
      && current.locationId === next.locationId
        ? current
        : next
    ));
  }, [initialFactionId, initialItemType, initialLocationId, initialOwnerId, initialQ, initialStatus]);

  useEffect(() => {
    if (previousRequestedIdRef.current !== requestedItemId) {
      previousRequestedIdRef.current = requestedItemId;
      appliedRequestedKeyRef.current = null;
      if (requestedItemId) setInvalidRequestedId("");
    }
  }, [requestedItemId]);

  const rows = useMemo(() => {
    const normalizedSearch = filters.q.trim().toLowerCase();
    return sourceItems.filter((item) => (
      (!normalizedSearch || [item.name, item.description, item.item_type, ...item.aliases, ...item.tags]
        .some((value) => value.toLowerCase().includes(normalizedSearch)))
      && (filters.itemType === "all" || item.item_type === filters.itemType)
      && (view === "trash" || filters.status === "all" || latestFacts[item.item_id]?.values?.lifecycle_status === filters.status)
      && (view === "trash" || filters.ownerId === "all" || latestFacts[item.item_id]?.values?.owner_character_id === filters.ownerId)
      && (view === "trash" || filters.factionId === "all" || latestFacts[item.item_id]?.values?.controlling_faction_id === filters.factionId)
      && (view === "trash" || filters.locationId === "all" || latestFacts[item.item_id]?.values?.current_location_id === filters.locationId)
    )).sort((left, right) => (
      view === "items" ? left.order_index - right.order_index : left.name.localeCompare(right.name)
    ));
  }, [filters, sourceItems, view, latestFacts]);

  const filtersActive = filters.q.trim() !== ""
    || filters.itemType !== "all"
    || view === "items" && (filters.status !== "all"
    || filters.ownerId !== "all"
    || filters.factionId !== "all"
    || filters.locationId !== "all");
  const rowIds = useMemo(() => new Set(rows.map((item) => item.item_id)), [rows]);
  const selectedItem = rows.find((item) => item.item_id === selectedItemId) ?? null;
  const inlineSession = selectedItem ? inlineSessions[selectedItem.item_id] : undefined;
  useAssistantResource(selectedItem ? { resource_type: "item", id: selectedItem.item_id, name: selectedItem.name, version: selectedItem.version, draft: inlineSession ? { text: JSON.stringify(inlineSession.draft), fields: Object.keys(inlineSession.draft), version: inlineSession.source.version } : undefined } : null);
  const requestedSelectionKey = requestedItemId
    ? JSON.stringify([view, requestedItemId, filters.q, filters.itemType, filters.status, filters.ownerId, filters.factionId, filters.locationId])
    : null;

  useEffect(() => {
    if (
      !workspaceReady
      || loading
      || view !== initialView
      || filters.q !== initialQ
      || filters.itemType !== initialItemType
      || filters.status !== initialStatus
      || filters.ownerId !== initialOwnerId
      || filters.factionId !== initialFactionId
      || filters.locationId !== initialLocationId
    ) return;
    if (requestedItemId) {
      if (appliedRequestedKeyRef.current === requestedSelectionKey) {
        if (!rowIds.has(selectedItemId)) setSelectedItemId(rows[0]?.item_id ?? "");
        return;
      }
      if (rowIds.has(requestedItemId)) {
        appliedRequestedKeyRef.current = requestedSelectionKey;
        setSelectedItemId(requestedItemId);
        setInvalidRequestedId("");
      } else if (sourceItems.some((item) => item.item_id === requestedItemId)) {
        appliedRequestedKeyRef.current = requestedSelectionKey;
        setSelectedItemId(rows[0]?.item_id ?? "");
        setInvalidRequestedId("");
        onItemChange?.(view, null, filters, true);
      } else if (invalidRequestedId !== requestedItemId) {
        appliedRequestedKeyRef.current = requestedSelectionKey;
        setSelectedItemId("");
        setInvalidRequestedId(requestedItemId);
        onItemChange?.(view, null, filters, true);
      }
      return;
    }
    if (!rowIds.has(selectedItemId)) setSelectedItemId(rows[0]?.item_id ?? "");
  }, [filters, initialFactionId, initialItemType, initialLocationId, initialOwnerId, initialQ, initialStatus, initialView, invalidRequestedId, loading, onItemChange, requestedItemId, requestedSelectionKey, rowIds, rows, selectedItemId, sourceItems, view, workspaceReady]);

  const itemTypes = useMemo(
    () => Array.from(new Set([...items, ...trash].map((item) => item.item_type))).sort(),
    [items, trash],
  );

  const updateFilters = (next: ItemWorkspaceFilters) => {
    if (saving) return;
    if (requestedItemId) {
      appliedRequestedKeyRef.current = JSON.stringify([view, requestedItemId, next.q, next.itemType, next.status, next.ownerId, next.factionId, next.locationId]);
    }
    setFilters(next);
    setSelectedItemId("");
    setInvalidRequestedId("");
    setMobileDetailOpen(false);
    onItemChange?.(view, null, next, false);
  };

  const changeView = (nextView: ItemsWorkspaceView) => {
    if (saving) return;
    if (nextView === view) return;
    if (requestedItemId) {
      appliedRequestedKeyRef.current = JSON.stringify([nextView, requestedItemId, filters.q, filters.itemType, filters.status, filters.ownerId, filters.factionId, filters.locationId]);
    }
    setView(nextView);
    setSelectedItemId("");
    setInvalidRequestedId("");
    setMobileDetailOpen(false);
    setPageActionError("");
    onItemChange?.(nextView, null, filters, false);
  };

  const selectItem = (itemId: string) => {
    if (saving) return;
    setSelectedItemId(itemId);
    setInvalidRequestedId("");
    setMobileDetailOpen(true);
    onItemChange?.(view, itemId, filters, false);
    requestAnimationFrame(() => {
      const detail = document.getElementById(`item-detail-${itemId}`);
      if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
        detail.focus();
      }
    });
  };

  const openCreate = () => {
    if (!novelId) return;
    void startFact({ key: crypto.randomUUID(), revision: 1, novelId, operation: "create", kind: "start", candidate: structuredClone(EMPTY_ITEM),
      after: { lifecycle_status: "available", owner_character_id: null, controlling_faction_id: null, current_location_id: null },
      position: null, note: "", evidence: null, reason: "", resolves: [] }).catch((failure) => setPageActionError(failure.message));
  };

  const openEdit = (item: ItemReadV1, section: ItemEditorSection) => {
    if (busy || inlineSessions[item.item_id]) return;
    const nextDraft = {
      name: item.name,
      aliases: [...item.aliases],
      item_type: item.item_type,
      description: item.description,
      appearance: item.appearance,
      origin: item.origin,
      abilities: [...item.abilities],
      limitations: [...item.limitations],
      costs: [...item.costs],
      owner_character_id: item.owner_character_id,
      controlling_faction_id: item.controlling_faction_id,
      current_location_id: item.current_location_id,
      lifecycle_status: item.lifecycle_status,
      story_function: item.story_function,
      tags: [...item.tags],
    };
    // 草稿保留开始编辑时的版本；刷新资料不能悄悄改变保存基准。
    setInlineSessions((current) => ({ ...current, [item.item_id]: { section, source: item, draft: nextDraft, error: "", fieldErrors: {} } }));
    requestAnimationFrame(() => document.getElementById(`item-editor-${item.item_id}`)?.querySelector<HTMLElement>("input, select, textarea")?.focus());
  };

  const saveEditor = async (session: ItemInlineSession) => {
    const targetEditor = { source: session.source };
    const targetDraft = session.draft;
    const reportError = (message: string, errors: ApiFieldErrors = {}) => {
      setInlineSessions((current) => ({ ...current, [session.source.item_id]: { ...session, error: message, fieldErrors: errors } }));
      if (message) requestAnimationFrame(() => {
        const root = document.getElementById(`item-editor-${session.source.item_id}`);
        const field = Object.keys(errors)[0];
        const target = (field ? root?.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`) : null) ?? root?.querySelector<HTMLElement>("[data-editor-error-summary]");
        target?.focus();
      });
    };
    if (!targetEditor || !novelId) return;
    const fieldErrors: ApiFieldErrors = {};
    if (!targetDraft.name.trim()) fieldErrors.name = [t("validation.nameRequired")];
    if (!targetDraft.item_type.trim()) fieldErrors.item_type = [t("validation.typeRequired")];
    if (!targetDraft.description.trim()) fieldErrors.description = [t("validation.descriptionRequired")];
    if (targetDraft.lifecycle_status === "held" && !targetDraft.owner_character_id && !targetDraft.controlling_faction_id) {
      fieldErrors.lifecycle_status = [t("validation.heldRequiresHolder")];
    }
    for (const [field, values] of ([
      ["abilities", targetDraft.abilities],
      ["limitations", targetDraft.limitations],
      ["costs", targetDraft.costs],
    ] as const)) {
      if (values.some((value) => value.length > 500)) fieldErrors[field] = [t("validation.entryTooLong")];
    }
    if (session) {
      for (const field of Object.keys(fieldErrors)) if (!SECTION_FIELDS[session.section].includes(field as keyof ItemFieldsV1)) delete fieldErrors[field];
    }
    if (Object.keys(fieldErrors).length > 0) {
      reportError(t("errors.validation"), fieldErrors);
      return;
    }

    const fields: ItemFieldsV1 = {
      name: targetDraft.name.normalize("NFKC").trim(),
      aliases: targetDraft.aliases.map((value) => value.normalize("NFKC").trim()),
      item_type: targetDraft.item_type.normalize("NFKC").trim(),
      description: targetDraft.description.normalize("NFKC").trim(),
      appearance: targetDraft.appearance.normalize("NFKC").trim(),
      origin: targetDraft.origin.normalize("NFKC").trim(),
      abilities: targetDraft.abilities.map((value) => value.normalize("NFKC").trim()),
      limitations: targetDraft.limitations.map((value) => value.normalize("NFKC").trim()),
      costs: targetDraft.costs.map((value) => value.normalize("NFKC").trim()),
      owner_character_id: targetDraft.owner_character_id,
      controlling_faction_id: targetDraft.controlling_faction_id,
      current_location_id: targetDraft.current_location_id,
      lifecycle_status: targetDraft.lifecycle_status,
      story_function: targetDraft.story_function.normalize("NFKC").trim(),
      tags: targetDraft.tags.map((value) => value.normalize("NFKC").trim()),
    };

    setSaving(true);
    reportError("");
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    let saveCompleted = false;
    try {
        const payload: ItemUpdateV1 = { ...Object.fromEntries(SECTION_FIELDS[session!.section].map((field) => [field, fields[field]])), expected_version: targetEditor.source.version };
        const result = await apiPut<unknown>(
          `/api/items/novel/${novelId}/${targetEditor.source.item_id}`,
          payload,
          { signal: controller.signal },
        );
        const saved = parseItemReadV1(result, novelId);
        if (
          saved.item_id !== targetEditor.source.item_id
          || saved.version !== targetEditor.source.version + 1
          || saved.lifecycle_status !== targetEditor.source.lifecycle_status
          || saved.is_deleted
          || SECTION_FIELDS[session!.section].some((field) => JSON.stringify(saved[field]) !== JSON.stringify(fields[field]))
        ) throw new Error("Invalid item update response");
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      const savedView: ItemsWorkspaceView = saved.is_deleted ? "trash" : "items";
      setView(savedView);
      setSelectedItemId(saved.item_id);
      setItems((current) => {
        const next = current.filter((item) => item.item_id !== saved.item_id);
        if (!saved.is_deleted) next.push(saved);
        return next.sort((left, right) => left.order_index - right.order_index);
      });
      setTrash((current) => {
        const next = current.filter((item) => item.item_id !== saved.item_id);
        if (saved.is_deleted) next.push(saved);
        return next;
      });
      if (session) {
        setInlineSessions((current) => ({ ...current, [saved.item_id]: undefined }));
      }
      saveCompleted = true;
      onFormalFactsChanged?.();
      await loadWorkspace();
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      onItemChange?.(savedView, saved.item_id, filters, false);
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      if (error instanceof ApiRequestError) {
        const normalized: ApiFieldErrors = {};
        for (const [field, messages] of Object.entries(error.fieldErrors)) {
          const formField = field.split(".").find((part) => Object.prototype.hasOwnProperty.call(EMPTY_ITEM, part)) ?? field;
          normalized[formField] = [...(normalized[formField] ?? []), ...messages];
        }
        reportError(error.status === 409 ? t("errors.conflict") : error.message, normalized);
      } else {
        reportError(t("errors.save"));
      }
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) {
        setSaving(false);
        if (saveCompleted && session) requestAnimationFrame(() => document.getElementById(`item-edit-${session.source.item_id}-${session.section}`)?.focus({ preventScroll: true }));
      }
    }
  };

  const openConfirm = async (intent: ConfirmIntent) => {
    setConfirmIntent(intent);
    setImpact(null);
    setConfirmError("");
    if (intent.kind === "restore") return;
    setImpactLoading(true);
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      const result = await apiGet<unknown>(
        `/api/items/novel/${novelId}/${intent.item.item_id}/delete-impact`,
        { signal: controller.signal },
      );
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setImpact(parseItemDeleteImpactV1(result, intent.item.item_id));
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setConfirmError(error instanceof ApiRequestError ? error.message : t("errors.impact"));
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setImpactLoading(false);
    }
  };

  const runConfirmAction = async () => {
    if (!confirmIntent || !novelId) return;
    const { item } = confirmIntent;
    setActionItemId(item.item_id);
    setConfirmError("");
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      if (confirmIntent.kind === "soft-delete") {
        const result = await apiDelete<unknown>(
          `/api/items/novel/${novelId}/${item.item_id}?expected_version=${item.version}`,
          { signal: controller.signal },
        );
        const deleted = parseItemReadV1(result, novelId);
        if (deleted.item_id !== item.item_id || deleted.version !== item.version + 1 || !deleted.is_deleted) {
          throw new Error("Invalid item delete response");
        }
      } else if (confirmIntent.kind === "restore") {
        const result = await apiPost<unknown>(
          `/api/items/novel/${novelId}/${item.item_id}/restore`,
          { expected_version: item.version },
          { signal: controller.signal },
        );
        const restored = parseItemReadV1(result, novelId);
        if (restored.item_id !== item.item_id || restored.version !== item.version + 1 || restored.is_deleted) {
          throw new Error("Invalid item restore response");
        }
      } else {
        const result = await apiDelete<unknown>(
          `/api/items/novel/${novelId}/${item.item_id}/hard?expected_version=${item.version}`,
          { signal: controller.signal },
        );
        parseItemHardDeleteResponseV1(result, item.item_id);
      }
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setSelectedItemId("");
      setMobileDetailOpen(false);
      setConfirmIntent(null);
      onFormalFactsChanged?.();
      await loadWorkspace();
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      onItemChange?.(view, null, filters, true);
      requestAnimationFrame(() => document.getElementById(`${TAB_PREFIX}-${view}-tab`)?.focus());
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setConfirmError(error instanceof ApiRequestError
        ? error.status === 409 ? t("errors.conflict") : error.message
        : t("errors.action"));
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setActionItemId("");
    }
  };

  const handleRosterKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextId = "";
    if (event.key === "ArrowUp") nextId = rows[Math.max(0, index - 1)]?.item_id ?? "";
    if (event.key === "ArrowDown") nextId = rows[Math.min(rows.length - 1, index + 1)]?.item_id ?? "";
    if (event.key === "Home") nextId = rows[0]?.item_id ?? "";
    if (event.key === "End") nextId = rows.at(-1)?.item_id ?? "";
    if (!nextId) return;
    event.preventDefault();
    selectItem(nextId);
    requestAnimationFrame(() => document.getElementById(`item-roster-${nextId}`)?.focus());
  };

  if (!canUseSavedNovel) {
    return (
      <section className="grid h-full min-h-72 place-items-center bg-background px-5 py-10">
        <div className="w-full max-w-xl border-y border-border py-10 text-center">
          <svg className="mx-auto size-7 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m7.5 4.27 9 5.15" /><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" /></svg>
          <h1 className="mt-3 text-xl font-semibold text-foreground">{t("disabled.title")}</h1>
        </div>
      </section>
    );
  }

  const activeCharacters = characters.filter((item) => !item.is_deleted && item.status === "active");
  const resumeOwnerCheck = (draft: ChapterRecordDraft) => {
    if (!novelId || !draft.itemOwner) return;
    const itemId = draft.itemOwner.item_id;
    setClosedPreparation(null); setOwnerSaved(false);
    setOwnerEntryVersion((version) => version + 1);
    setOwnerSession({ novelId, itemId, item: [...items, ...trash].find((item) => item.item_id === itemId) ?? null, draft, entryVersion: ownerEntryVersion + 1, closed: false });
  };
  const activeFactions = factions.filter((item) => !item.is_deleted && item.active_status === "active");
  const activeLocations = locations.filter((item) => !item.is_deleted && item.status === "active");

  const toolbar = (
    <section data-entity-toolbar className="workspace-toolbar flex min-w-0 flex-[1_1_640px] flex-wrap items-end gap-3">
      <Field label={t("filters.search")} className="flex-[2_1_200px]">
        <span className="relative block min-w-0">
          <input aria-label={t("filters.search")} disabled={saving} value={filters.q} onChange={(event) => updateFilters({ ...filters, q: event.target.value })} placeholder={t("filters.searchPlaceholder")} className={`${FILTER_CLASS} w-full pr-11`} />
          {filtersActive && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("actions.clearFilters")} title={t("actions.clearFilters")} disabled={saving} onClick={() => updateFilters(DEFAULT_FILTERS)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}
        </span>
      </Field>
      <Field label={t("filters.type")} className="flex-[1_1_112px]">
        <select disabled={saving} value={filters.itemType} onChange={(event) => updateFilters({ ...filters, itemType: event.target.value })} className={FILTER_CLASS}>
          <option value="all">{t("filters.allTypes")}</option>
          {itemTypes.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </Field>
      {view === "items" && <>
      <Field label={t("filters.status")} className="flex-[1_1_112px]">
        <select disabled={saving} value={filters.status} onChange={(event) => updateFilters({ ...filters, status: event.target.value as ItemWorkspaceFilters["status"] })} className={FILTER_CLASS}>
          <option value="all">{t("filters.allStatuses")}</option>
          {ITEM_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
        </select>
      </Field>
      <Field label={t("filters.owner")} className="flex-[1_1_112px]" error={referenceErrors.character} errorId="item-filter-owner-error">
        <select value={filters.ownerId} onChange={(event) => updateFilters({ ...filters, ownerId: event.target.value })} className={FILTER_CLASS} disabled={saving || Boolean(referenceErrors.character)} aria-describedby={referenceErrors.character ? "item-filter-owner-error" : undefined}>
          <option value="all">{t("filters.allOwners")}</option>
          {activeCharacters.map((character) => <option key={character.character_id} value={character.character_id}>{formatStableReferenceLabel(character.name, character.character_id)}</option>)}
        </select>
      </Field>
      <Field label={t("filters.faction")} className="flex-[1_1_112px]" error={referenceErrors.faction} errorId="item-filter-faction-error">
        <select value={filters.factionId} onChange={(event) => updateFilters({ ...filters, factionId: event.target.value })} className={FILTER_CLASS} disabled={saving || Boolean(referenceErrors.faction)} aria-describedby={referenceErrors.faction ? "item-filter-faction-error" : undefined}>
          <option value="all">{t("filters.allFactions")}</option>
          {activeFactions.map((faction) => <option key={faction.faction_id} value={faction.faction_id}>{formatStableReferenceLabel(faction.name, faction.faction_id)}</option>)}
        </select>
      </Field>
      <Field label={t("filters.location")} className="flex-[1_1_112px]" error={referenceErrors.location} errorId="item-filter-location-error">
        <select value={filters.locationId} onChange={(event) => updateFilters({ ...filters, locationId: event.target.value })} className={FILTER_CLASS} disabled={saving || Boolean(referenceErrors.location)} aria-describedby={referenceErrors.location ? "item-filter-location-error" : undefined}>
          <option value="all">{t("filters.allLocations")}</option>
          {activeLocations.map((location) => <option key={location.location_id} value={location.location_id}>{formatStableReferenceLabel(location.name, location.location_id)}</option>)}
        </select>
      </Field>
      </>}
      <div className="flex shrink-0 flex-wrap gap-2">
        {view === "items" && <Button variant="outline" size="sm" onPress={openCreate} isDisabled={busy || !workspaceReady}>{t("actions.create")}</Button>}
      </div>
    </section>
  );

  return (
    <section ref={workspaceRef} className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b border-border bg-surface">
        <h1 className="sr-only">{t("title")}</h1>
        {dataError && workspaceReady && (
          <div className="flex flex-col gap-3 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200 sm:flex-row sm:items-center sm:justify-between sm:px-6" role="alert">
            <span>{dataError}</span>
            <Button size="sm" variant="outline" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
          </div>
        )}
        <div className="flex min-h-11 items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 gap-5 overflow-x-auto" role="tablist" aria-label={t("title")}>
            {(["items", "trash"] as const).map((tab, index, tabs) => (
              <button
                key={tab}
                id={`${TAB_PREFIX}-${tab}-tab`}
                type="button"
                role="tab"
                disabled={saving}
                aria-selected={view === tab}
                aria-controls={`${TAB_PREFIX}-${tab}-panel`}
                tabIndex={view === tab ? 0 : -1}
                onClick={() => changeView(tab)}
                onKeyDown={(event) => {
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                  const nextTab = tabs[nextIndex];
                  changeView(nextTab);
                  document.getElementById(`${TAB_PREFIX}-${nextTab}-tab`)?.focus();
                }}
                className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${view === tab ? "border-accent text-accent" : "border-transparent text-muted hover:border-border hover:text-foreground"}`}
              >
                {t(`tabs.${tab}`)}
                <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs tabular-nums text-muted">{tab === "items" ? items.length : trash.length}</span>
              </button>
            ))}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <SectionActionButton action="refresh" label={loading ? t("actions.refreshing") : t("actions.refresh")} variant="ghost" size="sm" onPress={() => {
              setCandidateReviewing(false);
              setCandidateSessionKey((current) => current + 1);
              setFactReadRefresh((current) => current + 1);
              void loadWorkspace();
            }} isDisabled={busy} />
          </div>
        </div>
      </header>

      <div id={`${TAB_PREFIX}-${view}-panel`} data-entity-body role="tabpanel" aria-labelledby={`${TAB_PREFIX}-${view}-tab`} className="@container/master flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 sm:px-6">
        {(factPreparations.length > 0 || factDrafts.length > 0) && <div className="flex shrink-0 flex-wrap gap-2" aria-label={f("localDrafts", { count: factPreparations.length + factDrafts.length })}>
          {factPreparations.map((row) => <DraftChip key={row.key} label={row.target?.name || row.candidate?.name || f(row.generation ? "prepareBatch" : "untitledDraft")} isDisabled={busy || Boolean(factPreparation || factDraft)} onResume={() => setFactPreparation(row)}
            onDiscard={!row.origin && !row.returnedToCheck ? async () => {
              await discardItemFactPreparation(row);
              setClosedPreparation((current) => current?.key === row.key ? null : current);
              setFactPreparations((rows) => rows.filter((current) => current.key !== row.key));
            } : undefined} />)}
          {factDrafts.map((row) => <DraftChip key={row.key} label={row.schema_id === "item.fact.batch.draft" ? f("confirmBatch") : row.preview.basis.target.kind === "new" ? row.preview.basis.target.candidate.name : row.preview.basis.target.name} status={row.command?.saved ? "saved" : row.command ? row.command.unknown ? "pending" : "rejected" : "draft"} isDisabled={busy || Boolean(factPreparation || factDraft)} onResume={() => setFactDraft(row)}
            onDiscard={!(row.schema_id === "item.fact.draft" && row.origin) && !row.returnedToCheck && (!row.command || row.command.saved && row.command.readbackDone) ? async () => {
              await writeFactDraft(row.schema_id === "item.fact.batch.draft" ? "item_batch" : "item", `${novelId}:${row.schema_id === "item.fact.batch.draft" ? "item-fact-batches" : "item-facts"}`, row, row.revision, true);
              setFactDrafts((rows) => rows.filter((current) => current.key !== row.key));
            } : undefined} />)}
        </div>}
        {reviewKey && <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border pb-3">
          {!currentReview && <p role="status" className="text-sm text-muted">{t("loading")}</p>}
          {currentReview?.error && <><RelationEditorErrorSummary message={currentReview.error} /><Button size="sm" variant="outline" onPress={() => setOwnerEntryVersion((version) => version + 1)}>{t("actions.retry")}</Button></>}
          {currentReview?.value && onNavigateChapter && <Button data-testid="chapter-review-return-chapter" size="sm" variant="ghost" isDisabled={ownerBusy} onPress={() => {
            if (active && chapterId && chapterReviewId) onNavigateChapter(chapterId, chapterReviewId);
          }}>{tRecords("review.backToChapter")}</Button>}
          {currentReviewMember?.draft && <Button data-testid="chapter-review-continue-item" size="sm" variant="outline" isDisabled={ownerBusy || Boolean(ownerSession && !ownerSession.closed)} onPress={() => {
            if (!active || !novelId || !currentReviewMember.draft) return;
            const restored = currentReviewMember.draft;
            const itemId = restored.itemOwner!.item_id;
            setOwnerSaved(false);
            setOwnerSession({ novelId, itemId, item: [...items, ...trash].find((item) => item.item_id === itemId) ?? null, draft: restored, entryVersion: ownerEntryVersion, closed: false });
          }}>{tRecords("review.continueItem")}</Button>}
          {currentReview?.value && !currentReviewMember?.draft && <p role="status" className="text-sm text-muted">{tRecords(currentReviewMember?.operation?.saved ? "saved" : "review.notFound")}</p>}
        </div>}
        <div className={candidateReviewing
          ? "contents"
          : `flex shrink-0 flex-wrap items-end gap-3 border-b border-border pb-3 [&>div:not([hidden])]:contents ${mobileDetailOpen ? "hidden @min-[800px]/master:flex" : ""}`}>
          {!candidateReviewing && toolbar}
          <RetainedViews activeKey={view === "items" && novelId ? novelId : null}>
          {novelId && (
            <ItemCandidateWorkspace
              key={`${novelId}:${candidateSessionKey}`}
              novelId={novelId}
              items={items}
              characters={characters}
              factions={factions}
              locations={locations}
              disabled={loading || saving || Boolean(actionItemId) || !workspaceReady}
              onReviewingChange={setCandidateReviewing}
              onBusyChange={setCandidateBusy}
              onPrepare={async (generation) => {
                await startFact({ key: crypto.randomUUID(), revision: 1, novelId, operation: "create", kind: "start", generation: structuredClone(generation), position: null, note: "", evidence: null,
                  after: { lifecycle_status: "available", owner_character_id: null, controlling_faction_id: null, current_location_id: null }, reason: "", resolves: [] });
              }}
            />
          )}
          </RetainedViews>
        </div>

        {!candidateReviewing && (
          <>
        {pageActionError && <div className="shrink-0 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">{pageActionError}</div>}
        {ownerSaved && <p role="status" className="shrink-0 px-4 py-3 text-sm">{tRecords("saved")}</p>}

        {dataError && !workspaceReady ? (
          <div className="border-y border-red-500/40 bg-red-50 px-5 py-14 text-center text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
            <p className="text-sm font-medium">{dataError}</p>
            <Button className="mt-5" size="sm" variant="outline" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
          </div>
        ) : loading && sourceItems.length === 0 ? (
          <div className="border-y border-border px-5 py-14 text-center" role="status">
            <span className="mx-auto block size-6 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" />
            <p className="mt-3 text-sm text-muted">{t("loading")}</p>
          </div>
        ) : invalidRequestedId ? (
          <div className="border-y border-dashed border-border px-5 py-14 text-center" role="alert">
            <p className="text-sm font-medium text-foreground">{t("invalid.title")}</p>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">{t("invalid.description", { id: invalidRequestedId })}</p>
            <Button className="mt-5" size="sm" variant="outline" onPress={() => {
              const firstId = rows[0]?.item_id ?? "";
              setInvalidRequestedId("");
              setSelectedItemId(firstId);
              onItemChange?.(view, firstId || null, filters, true);
              requestAnimationFrame(() => {
                const targetId = firstId ? `item-roster-${firstId}` : `${TAB_PREFIX}-${view}-tab`;
                document.getElementById(targetId)?.focus();
              });
            }}>{t("actions.backToRoster")}</Button>
          </div>
        ) : rows.length === 0 ? (
          <div className="border-y border-dashed border-border px-5 py-14 text-center">
            <p className="text-sm font-medium text-foreground">{filtersActive ? t("empty.filteredTitle") : view === "trash" ? t("empty.trashTitle") : t("empty.itemsTitle")}</p>
            {!filtersActive && view === "items" && <Button className="mt-5" variant="primary" size="sm" onPress={openCreate} isDisabled={busy || !workspaceReady}>{t("actions.createFirst")}</Button>}
          </div>
        ) : selectedItem && (
          <div className={`grid min-h-[520px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${hideList ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
            <div className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
            <aside data-entity-roster id={`item-list-${novelId}-${view}`} className={`${hideList ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`} aria-label={t(`tabs.${view}`)} aria-hidden={hideList || undefined} inert={hideList} tabIndex={0}>
              <ul className="divide-y divide-border">
                {rows.map((item, index) => (
                  <li key={item.item_id}>
                    <button
                      disabled={saving} id={`item-roster-${item.item_id}`}
                      type="button"
                      aria-current={selectedItem.item_id === item.item_id ? "true" : undefined}
                      tabIndex={selectedItem.item_id === item.item_id ? 0 : -1}
                      onClick={() => selectItem(item.item_id)}
                      onKeyDown={(event) => handleRosterKeyDown(event, index)}
                      className={`block min-h-16 w-full px-4 py-3 text-left transition-colors ${selectedItem.item_id === item.item_id ? "bg-selected" : "hover:bg-surface-secondary/55"}`}
                    >
                      <span className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-semibold text-foreground">{item.name}</span>
                        <span className="shrink-0 text-xs font-medium text-muted">{latestFacts[item.item_id]?.values ? t(`status.${latestFacts[item.item_id].values!.lifecycle_status}`) : f("unknown")}</span>
                      </span>
                      <span className="mt-1 block truncate text-xs text-muted">{item.item_type}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </aside>
            <SidebarEdgeHandle controls={`item-list-${novelId}-${view}`} className="hidden @min-[800px]/master:flex"
              leftAction={hideList ? undefined : { label: tLayout("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }}
              rightAction={hideList ? { label: tLayout("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined}
            />
            </div>

            <article id={`item-detail-${selectedItem.item_id}`} className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0`} aria-label={`${t(`tabs.${view}`)} · ${selectedItem.name}`} tabIndex={0}>
              <button type="button" disabled={saving} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
                setMobileDetailOpen(false);
                requestAnimationFrame(() => document.getElementById(`item-roster-${selectedItem.item_id}`)?.focus());
              }}>← {t("actions.backToRoster")}</button>
              <div data-entity-detail className="min-w-0 px-5 py-4 sm:px-7">
                <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2">
                      <Pill terminal={TERMINAL_ITEM_STATUSES.has(latestFacts[selectedItem.item_id]?.values?.lifecycle_status ?? "available")}>{latestFacts[selectedItem.item_id]?.values ? t(`status.${latestFacts[selectedItem.item_id].values!.lifecycle_status}`) : f("unknown")}</Pill>
                    </div>
                    <h2 className="sr-only">{selectedItem.name}</h2>
                    <p className="mt-1 font-mono text-xs text-muted">{selectedItem.item_id} · v{selectedItem.version}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {view === "items" ? (
                      <>
                        <SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" onPress={() => void openConfirm({ kind: "soft-delete", item: selectedItem })} isDisabled={busy || Boolean(inlineSession)} />
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onPress={() => setConfirmIntent({ kind: "restore", item: selectedItem })} isDisabled={busy}>{t("actions.restore")}</Button>
                        <Button size="sm" variant="ghost" className="text-danger" onPress={() => void openConfirm({ kind: "hard-delete", item: selectedItem })} isDisabled={busy}>{t("actions.hardDelete")}</Button>
                      </>
                    )}
                  </div>
                </header>

                <div className="mt-4 space-y-4">
                  {(["identity", "profile", "capabilities", "references", "story"] as const).map((section, index) => {
                    const editing = view === "items" && inlineSession?.section === section;
                    return <DocumentSection key={section} number={String(index + 1).padStart(2, "0")} title={section === "references" ? f("title") : t(`editor.sections.${section}`)} actions={section !== "references" && view === "items" && (editing ? <>
                      <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" isDisabled={saving} onPress={() => {
                        setInlineSessions((current) => ({ ...current, [selectedItem.item_id]: undefined }));
                        requestAnimationFrame(() => document.getElementById(`item-edit-${selectedItem.item_id}-${section}`)?.focus({ preventScroll: true }));
                      }} />
                      <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" isDisabled={busy} onPress={() => void saveEditor(inlineSession)} />
                    </> : <SectionEditButton id={`item-edit-${selectedItem.item_id}-${section}`} isDisabled={busy || Boolean(inlineSession)} onPress={() => openEdit(selectedItem, section)} label={t("actions.edit")} />)}>
                      {editing ? <div id={`item-editor-${selectedItem.item_id}`} className="space-y-4">
                        {inlineSession.error && <RelationEditorErrorSummary message={inlineSession.error} fieldErrors={inlineSession.fieldErrors} />}
                        {inlineSession.error === t("errors.conflict") && selectedItem.version !== inlineSession.source.version && <Button size="sm" variant="outline" isDisabled={saving} onPress={() => {
                          // 只有作者明确采用时才更新版本，并保留当前节的修改。
                          setInlineSessions((current) => ({ ...current, [selectedItem.item_id]: { ...inlineSession,
                            source: selectedItem, draft: { ...selectedItem, ...Object.fromEntries(SECTION_FIELDS[section].map((field) => [field, inlineSession.draft[field]])) }, error: "", fieldErrors: {},
                          } }));
                        }}>{t("actions.useLatest")}</Button>}
                        <ItemFieldsForm section={section} value={inlineSession.draft} characters={characters} factions={factions} locations={locations} disabled={saving} statusEditable={false} referenceErrors={referenceErrors} fieldErrors={inlineSession.fieldErrors} errorIdPrefix={`item-${selectedItem.item_id}`} onChange={(value) => setInlineSessions((current) => ({ ...current, [selectedItem.item_id]: { ...inlineSession, draft: value } }))} />
                      </div> : <dl className="detail-fields grid min-w-0 gap-4">
                        {section === "identity" && <>
                          <ReadOnlyField label={t("fields.name")} value={selectedItem.name} />
                          <ReadOnlyField label={t("fields.type")} value={selectedItem.item_type} />
                          <ReadOnlyField label={t("fields.aliases")} value={selectedItem.aliases.length ? <TagList values={selectedItem.aliases} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                          <ReadOnlyField wide label={t("fields.description")} value={selectedItem.description || t("empty.none")} />
                        </>}
                        {section === "profile" && <>
                          <ReadOnlyField wide label={t("fields.appearance")} value={selectedItem.appearance || t("empty.none")} />
                          <ReadOnlyField wide label={t("fields.origin")} value={selectedItem.origin || t("empty.none")} />
                        </>}
                        {section === "capabilities" && <>
                          <ReadOnlyField label={t("fields.abilities")} value={selectedItem.abilities.length ? <TagList values={selectedItem.abilities} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                          <ReadOnlyField label={t("fields.limitations")} value={selectedItem.limitations.length ? <TagList values={selectedItem.limitations} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                          <ReadOnlyField label={t("fields.costs")} value={selectedItem.costs.length ? <TagList values={selectedItem.costs} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                        </>}
                        {section === "story" && <>
                          <ReadOnlyField wide label={t("fields.storyFunction")} value={selectedItem.story_function || t("empty.none")} />
                          <ReadOnlyField label={t("fields.tags")} value={selectedItem.tags.length ? <TagList values={selectedItem.tags} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                        </>}
                      </dl>}
                      {section === "references" && novelId && <ItemFactsPanel key={`facts:${novelId}:${selectedItem.item_id}`} novelId={novelId} item={selectedItem} chapters={factChapters ?? []} choices={{ characters, factions, locations }} disabled={busy || Boolean(factPreparation || factDraft || inlineSession)} refresh={factReadRefresh} onPrepare={startFact} />}
                      {section === "references" && view === "items" && novelId && <ItemOwnerConfirmationEntry key={`${novelId}:${selectedItem.item_id}`} novelId={novelId} item={selectedItem} refresh={ownerEntryVersion} disabled={busy || Boolean(ownerSession && !ownerSession.closed) || Boolean(referenceErrors.character)} onStart={(restored) => { if (!active) return; setOwnerSaved(false); setOwnerSession({ novelId, itemId: selectedItem.item_id, item: selectedItem, draft: restored, entryVersion: ownerEntryVersion, closed: false }); }} />}
                    </DocumentSection>;
                  })}
                </div>
              </div>
            </article>
          </div>
        )}
          </>
        )}
      </div>

      {/* 固定启动目标；选择/筛选变化不能卸载尚未安全保稿或清理的确认会话。 */}
      {novelId && preparationDialog?.novelId === novelId && <ItemFactPreparationDialog key={`${preparationDialog.key}:${preparationDialog.revision}`} initialPreparation={preparationDialog} onReturnedToCheck={resumeOwnerCheck} isOpen={Boolean(factPreparation)} referenceErrors={referenceErrors} chapters={factChapters} choices={{ characters, factions, locations }} onBusy={setFactBusy} beforeLeaveRef={factBeforeLeave} onDiscarded={() => { setClosedPreparation(null); setFactPreparation(null); setFactRefresh((value) => value + 1); }} onClose={() => { setClosedPreparation(factPreparation); setFactPreparation(null); setFactRefresh((value) => value + 1); }} onPrepared={(prepared) => { setClosedPreparation(null); setFactPreparation(null); setFactDraft(prepared); setFactRefresh((value) => value + 1); }} />}
      {novelId && factDraft && <ItemFactConfirmationDialog key={factDraft.key} novelId={novelId} initialDraft={factDraft} onReturnedToCheck={resumeOwnerCheck} onReprepared={setFactPreparation} choices={{ characters, factions, locations }} onBusy={setFactBusy} beforeLeaveRef={factBeforeLeave} onClose={() => { setFactDraft(null); setFactRefresh((value) => value + 1); }} onReadback={async () => { await loadWorkspace(true); onFormalFactsChanged?.(); setOwnerEntryVersion((value) => value + 1); }} />}
      {ownerSession && novelId === ownerSession.novelId && <ItemOwnerConfirmation key={`${novelId}:${ownerSession.itemId}:${ownerSession.entryVersion}`} novelId={novelId} item={ownerSession.item} characters={characters} choices={{ characters, factions, locations }} onPrepareFact={setFactDraft} onResumePreparation={setFactPreparation} initialDraft={ownerSession.draft} onBusy={setOwnerBusy} onDirty={setOwnerDirty} beforeLeaveRef={ownerBeforeLeave} onReadback={(latest) => {
        // 回执后只合入当前正式物品；原位编辑的输入与开始版本保持原样。
        loadAbortRef.current?.abort(); loadRequestIdRef.current += 1; setLoading(false);
        setItems((current) => current.map((row) => row.item_id === latest.item_id && row.version <= latest.version ? latest : row));
        onFormalFactsChanged?.();
      }} onClose={(saved) => {
        // 保留已关闭的 ModalBackdrop 完成退出和焦点恢复，下次明确启动才替换宿主。
        setOwnerSession((current) => current ? { ...current, closed: true } : current);
        setOwnerEntryVersion((version) => version + 1); setOwnerSaved(saved);
      }} />}

      {confirmIntent && confirmIntent.kind === "restore" && (
        <ConfirmActionModal
          title={t("confirm.restore.title")}
          message={t("confirm.restore.message", { name: confirmIntent.item.name })}
          confirmText={t("confirm.restore.confirm")}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          error={confirmError}
          isLoading={actionItemId === confirmIntent.item.item_id}
          onCancel={() => { setConfirmIntent(null); setConfirmError(""); }}
          onConfirm={() => void runConfirmAction()}
        />
      )}

      {confirmIntent && confirmIntent.kind !== "restore" && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !actionItemId && setConfirmIntent(null)} variant="blur" isDismissable={!actionItemId}>
          <Modal.Container size="sm" scroll="inside">
            <Modal.Dialog className="w-full max-w-lg">
              <Modal.Header className="flex items-center justify-between gap-3 px-5 pb-0 pt-5">
                <Modal.Heading className="text-base font-semibold text-foreground">{t(`confirm.${confirmIntent.kind}.title`)}</Modal.Heading>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={Boolean(actionItemId)} />
              </Modal.Header>
              <Modal.Body className="px-5 py-4">
                <p className="text-sm leading-6 text-muted">{t(`confirm.${confirmIntent.kind}.message`, { name: confirmIntent.item.name })}</p>
                {impactLoading && <p className="mt-4 text-sm text-muted" role="status">{t("impact.loading")}</p>}
                {confirmError && <RelationEditorErrorSummary message={confirmError} className="mt-4" />}
                {impact && (
                  <div className="mt-4 border-y border-border py-4">
                    <h3 className="text-xs font-semibold tracking-normal text-accent">{t("impact.title")}</h3>
                    <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                      <ImpactCount label={t("impact.arcs")} value={impact.arcs} />
                      <ImpactCount label={t("impact.chapters")} value={impact.chapters} />
                      <ImpactCount label={t("impact.scenes")} value={impact.scenes} />
                      <ImpactCount label={t("impact.foreshadowings")} value={impact.foreshadowings} />
                    </dl>
                    {confirmIntent.kind === "hard-delete" && impact.has_protected_references && <p className="mt-4 text-sm font-medium text-danger">{t("impact.hardBlocked")}</p>}
                  </div>
                )}
              </Modal.Body>
              <Modal.Footer className="flex justify-end gap-2 px-5 pb-5 pt-0">
                <Button variant="ghost" size="sm" onPress={() => { setConfirmIntent(null); setConfirmError(""); }} isDisabled={Boolean(actionItemId)}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" className="bg-red-600 text-white hover:bg-red-700" onPress={() => void runConfirmAction()} isDisabled={impactLoading || !impact || Boolean(actionItemId) || (confirmIntent.kind === "hard-delete" && impact.has_protected_references)}>
                  {actionItemId ? t("actions.processing") : t(`confirm.${confirmIntent.kind}.confirm`)}
                </Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}
    </section>
  );
}

function Field({ label, children, className = "", error, errorId }: { label: string; children: ReactNode; className?: string; error?: string; errorId?: string }) {
  return <label className={`grid min-w-0 gap-1.5 text-xs font-medium text-muted ${className}`}><span>{label}</span>{children}{error && <span id={errorId} className="text-xs font-medium text-danger">{error}</span>}</label>;
}

function Pill({ children, terminal = false }: { children: ReactNode; terminal?: boolean }) {
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${terminal ? "bg-red-500/10 text-red-700 dark:text-red-300" : "bg-surface-secondary text-muted"}`}>{children}</span>;
}



function ImpactCount({ label, value }: { label: string; value: number }) {
  return <div><dt className="text-xs text-muted">{label}</dt><dd className="mt-1 font-semibold tabular-nums text-foreground">{value}</dd></div>;
}
