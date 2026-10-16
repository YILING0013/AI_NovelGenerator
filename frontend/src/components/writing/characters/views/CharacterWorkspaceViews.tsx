"use client";
import { useAssistantFocus, useAssistantResource } from "@/components/writing/assistant/AssistantContext";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";


import { useContext, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { TooltipHint } from "@/components/shared/TooltipHint";
import type { CoreFaction } from "@/types/novel";
import type {
  CharacterFactionBindingResponseV1,
  CharacterImportanceLevel,
  CharacterRelationResponseV1,
  CharacterResponseV1,
  CharacterRoleType,
} from "@/types/character";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import type { CharacterFactField, CharacterFactsAtPositionV1 } from "@/types/characterFacts";
import CharacterFactsPanel from "../CharacterFactsPanel";
import CharacterRelationDesignSection from "../CharacterRelationDesignSection";
import CharacterRelationFactsPanel from "../CharacterRelationFactsPanel";
import { CharacterProfileSections, type ProfileSectionUpdate } from "./CharacterDocumentDetails";

type CharactersTranslator = ReturnType<typeof useTranslations>;

/** 角色工作台当前展示的数据视图。 */
export type CharacterWorkspaceView = "profiles" | "relations" | "bindings" | "trash";

export interface UnavailablePanelProps {
  title: string;
  message: string;
}

export interface WorkspaceHeaderProps {
  view: CharacterWorkspaceView;
  characterCount: number;
  relationCount: number;
  bindingCount: number;
  trashCount: number;
  loading: boolean;
  saving?: boolean;
  onViewChange: (view: CharacterWorkspaceView) => void;
  onRefresh: () => void;
  t: CharactersTranslator;
}

export interface ProfilesViewProps {
  allCharacters: CharacterResponseV1[];
  characters: CharacterResponseV1[];
  allCharacterCount: number;
  search: string;
  roleFilter: "all" | CharacterRoleType;
  importanceFilter: "all" | CharacterImportanceLevel;
  relationCountByCharacter: ReadonlyMap<string, number>;
  loading: boolean;
  generationLocked: boolean;
  actionId: string;
  onSearchChange: (value: string) => void;
  onRoleFilterChange: (value: "all" | CharacterRoleType) => void;
  onImportanceFilterChange: (value: "all" | CharacterImportanceLevel) => void;
  onManualCreate: () => void;
  onGenerate: () => void;
  saving: boolean;
  onSave: (character: CharacterResponseV1, payload: ProfileSectionUpdate) => Promise<void>;
  onToggleStatus: (character: CharacterResponseV1) => void;
  onDelete: (character: CharacterResponseV1) => void;
  onFactsChanged?: () => Promise<void> | void;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  t: CharactersTranslator;
}

export interface RelationsViewProps {
  relations: CharacterRelationResponseV1[];
  activeCharacters: CharacterResponseV1[];
  coreCharacters: CharacterResponseV1[];
  characterNames: ReadonlyMap<string, string>;
  loading: boolean;
  generationLocked: boolean;
  actionId: string;
  onManualCreate: () => void;
  onGenerate: () => void;
  saving: boolean;
  onRelationChanged?: (relation: CharacterRelationResponseV1) => void;
  onFactsChanged?: () => Promise<void>;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  onCopy: (relation: CharacterRelationResponseV1) => void;
  onToggleActive: (relation: CharacterRelationResponseV1) => void;
  onDelete: (relation: CharacterRelationResponseV1) => void;
  t: CharactersTranslator;
}

export interface TrashViewProps {
  characters: CharacterResponseV1[];
  relations: CharacterRelationResponseV1[];
  actionId: string;
  onRestoreCharacter: (character: CharacterResponseV1) => void;
  onHardDeleteCharacter: (character: CharacterResponseV1) => void;
  onRestoreRelation: (relation: CharacterRelationResponseV1) => void;
  onHardDeleteRelation: (relation: CharacterRelationResponseV1) => void;
  t: CharactersTranslator;
}

export interface BindingsViewProps {
  saving: boolean;
  editingBindingId?: string;
  editor?: ReactNode;
  characters: CharacterResponseV1[];
  bindings: CharacterFactionBindingResponseV1[];
  factions: CoreFaction[];
  loading: boolean;
  actionId: string;
  onCreate: (character: CharacterResponseV1) => void;
  onEdit: (binding: CharacterFactionBindingResponseV1) => void;
  onToggleActive: (binding: CharacterFactionBindingResponseV1) => void;
  onMakePrimary: (binding: CharacterFactionBindingResponseV1) => void;
  onDelete: (binding: CharacterFactionBindingResponseV1) => void;
  onRestore: (binding: CharacterFactionBindingResponseV1) => void;
  onHardDelete: (binding: CharacterFactionBindingResponseV1) => void;
  t: CharactersTranslator;
}

export interface ModalLayerProps {
  title: string;
  description?: string;
  onClose: () => void;
  footer: ReactNode;
  children: ReactNode;
  dismissable?: boolean;
  busy?: boolean;
}

const ROLE_TYPES: CharacterRoleType[] = [
  "protagonist",
  "deuteragonist",
  "antagonist",
  "supporting",
  "minor",
];

const IMPORTANCE_LEVELS: CharacterImportanceLevel[] = [
  "core",
  "major",
  "supporting",
  "background",
];

const SYMMETRIC_CHARACTER_RELATION_TYPES = new Set<CharacterRelationResponseV1["relation_type"]>([
  "friend",
  "romantic",
  "ally",
  "rival",
  "enemy",
]);

const FILTER_CLASS =
  "min-h-10 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15";
const CHARACTER_WORKSPACE_TAB_PREFIX = "character-workspace";

/** 判断人物关系类型是否为无方向的对称关系。 */
export function isSymmetricCharacterRelation(
  type: CharacterRelationResponseV1["relation_type"],
): boolean {
  return SYMMETRIC_CHARACTER_RELATION_TYPES.has(type);
}

/**
 * 功能：渲染小说未保存时的角色功能不可用提示。
 * Args:
 *   props: 提示标题与说明文案。
 * Returns:
 *   居中展示的不可用状态 React 节点。
 */
export function UnavailablePanel({ title, message }: UnavailablePanelProps) {
  return (
    <section className="grid h-full min-h-72 place-items-center bg-background px-5 py-10">
      <div className="w-full max-w-xl border-y border-border py-10 text-center">
        <span className="text-2xl text-accent" aria-hidden="true">◇</span>
        <h2 className="mt-3 text-xl font-semibold text-foreground">{title}</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">{message}</p>
      </div>
    </section>
  );
}

/**
 * 显示角色页面的标签和刷新按钮。
 * Args:
 *   props: 当前页面、各项数量、加载状态和操作。
 * Returns:
 *   角色页面页头。
 */
export function WorkspaceHeader({
  view,
  characterCount,
  relationCount,
  bindingCount,
  trashCount,
  loading,
  saving = false,
  onViewChange,
  onRefresh,
  t,
}: WorkspaceHeaderProps) {
  const tabs: Array<{ value: CharacterWorkspaceView; label: string; count: number }> = [
    { value: "profiles", label: t("tabs.profiles"), count: characterCount },
    { value: "relations", label: t("tabs.relations"), count: relationCount },
    { value: "bindings", label: t("tabs.bindings"), count: bindingCount },
    { value: "trash", label: t("tabs.trash"), count: trashCount },
  ];

  return (
    <header className="shrink-0 border-b border-border bg-surface">
      <h1 className="sr-only">{t("title")}</h1>
      <div className="flex min-h-11 items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 gap-5 overflow-x-auto" role="tablist" aria-label={t("title")}>
          {tabs.map((tab, index) => (
            <button
              key={tab.value}
              id={`${CHARACTER_WORKSPACE_TAB_PREFIX}-${tab.value}-tab`}
              type="button"
              role="tab"
              aria-selected={view === tab.value}
              aria-controls={`${CHARACTER_WORKSPACE_TAB_PREFIX}-${tab.value}-panel`}
              tabIndex={view === tab.value ? 0 : -1}
              disabled={saving}
              onClick={() => onViewChange(tab.value)}
              onKeyDown={(event) => {
                if (saving || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const nextIndex = event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? tabs.length - 1
                    : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                const nextTab = tabs[nextIndex];
                onViewChange(nextTab.value);
                document.getElementById(`${CHARACTER_WORKSPACE_TAB_PREFIX}-${nextTab.value}-tab`)?.focus();
              }}
              className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors ${
                view === tab.value
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:border-border hover:text-foreground"
              }`}
            >
              {tab.label}
              <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs tabular-nums text-muted">{tab.count}</span>
            </button>
          ))}
        </div>
        <SectionActionButton action="refresh" label={loading ? t("loading") : t("refresh")} className="shrink-0" variant="ghost" size="sm" onPress={onRefresh} isDisabled={loading || saving} />
      </div>
    </header>
  );
}

/**
 * 功能：渲染角色名册与单一档案详情组成的主从工作台。
 * Args:
 *   props: 角色列表、筛选状态、势力归属数据与档案操作回调。
 * Returns:
 *   可响应桌面、平板和移动端布局的档案工作台 React 节点。
 */
export function ProfilesView({
  characters,
  allCharacters,
  allCharacterCount,
  search,
  roleFilter,
  importanceFilter,
  relationCountByCharacter,
  loading,
  generationLocked,
  actionId,
  onSearchChange,
  onRoleFilterChange,
  onImportanceFilterChange,
  onManualCreate,
  onGenerate,
  onSave,
  saving,
  onToggleStatus,
  onDelete,
  onFactsChanged,
  onBusyChange,
  beforeLeaveRef,
  t,
}: ProfilesViewProps) {
  const listT = useTranslations("writing.listLayout");
  const active = useContext(RetainedViewActive);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [selectedId, setSelectedId] = useState(characters[0]?.character_id ?? allCharacters[0]?.character_id ?? "");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [factsBusy, setFactsBusy] = useState(false);
  const [leavingFacts, setLeavingFacts] = useState(false);
  const [leaveError, setLeaveError] = useState("");
  const [searchInput, setSearchInput] = useState(search);
  const factsBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const leaveRequest = useRef(0);
  const alive = useRef(true);
  const selected = characters.find((item) => item.character_id === selectedId) ?? characters[0]
    ?? allCharacters.find((item) => item.character_id === selectedId) ?? allCharacters[0];
  const context = useRef({ active, characterId: selected?.character_id }); context.current = { active, characterId: selected?.character_id };
  const busy = saving || factsBusy || leavingFacts;
  useEffect(() => { alive.current = true; return () => { alive.current = false; leaveRequest.current += 1; }; }, []);
  useEffect(() => { setSearchInput(search); }, [search]);
  useEffect(() => { if (!selectedId && selected) setSelectedId(selected.character_id); }, [selectedId, selected]);
  useEffect(() => { onBusyChange?.(factsBusy || leavingFacts); return () => onBusyChange?.(false); }, [factsBusy, leavingFacts, onBusyChange]);
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (factsBusy || leavingFacts) throw new Error(t("actions.saving")); await factsBeforeLeaveRef.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  }, [beforeLeaveRef, factsBusy, leavingFacts, t]);
  const leaveFacts = async (change: () => void) => {
    if (saving || factsBusy) return;
    const request = ++leaveRequest.current;
    const characterId = selected?.character_id;
    setLeavingFacts(true); setLeaveError("");
    try {
      await factsBeforeLeaveRef.current?.();
      if (alive.current && request === leaveRequest.current && context.current.active && context.current.characterId === characterId) change();
    } catch (failure) {
      if (alive.current && request === leaveRequest.current) { setLeaveError(failure instanceof Error ? failure.message : String(failure)); setSearchInput(search); }
    } finally { if (alive.current && request === leaveRequest.current) setLeavingFacts(false); }
  };
  useAssistantFocus("character", (target) => { if (busy || !allCharacters.some((character) => character.character_id === target.id)) return false; void leaveFacts(() => { setSelectedId(target.id); setMobileDetailOpen(true); onSearchChange(""); onRoleFilterChange("all"); onImportanceFilterChange("all"); }); });
  const noResults = characters.length === 0 && allCharacters.length > 0;
  const filtersActive = Boolean(search) || roleFilter !== "all" || importanceFilter !== "all";

  // lg 以上让主从区域继承工作台剩余高度，窄屏继续采用自然单列滚动。
  return (
    <div
      id={`${CHARACTER_WORKSPACE_TAB_PREFIX}-profiles-panel`}
      role="tabpanel"
      aria-labelledby={`${CHARACTER_WORKSPACE_TAB_PREFIX}-profiles-tab`}
      className="@container/master flex h-full min-h-0 flex-col gap-3"
    >
      {leaveError && <RelationEditorErrorSummary message={leaveError} />}
      <section className={`shrink-0 border-b border-border pb-3 ${mobileDetailOpen && !noResults ? "hidden @min-[800px]/master:block" : ""}`}>
        <div data-entity-toolbar className="workspace-toolbar flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div className="grid flex-1 items-end gap-3 lg:grid-cols-[minmax(220px,1fr)_180px_180px]">
            <label className="grid gap-1.5 text-xs font-medium text-muted">
              <span>{t("filters.searchLabel")}</span>
              <span className="relative block min-w-0"><input type="search" aria-label={t("filters.searchLabel")} disabled={saving || factsBusy} value={searchInput} onChange={(event) => { const value = event.target.value; setSearchInput(value); void leaveFacts(() => onSearchChange(value)); }} placeholder={t("filters.searchPlaceholder")} className={`${FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`} />{filtersActive && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("filters.clear")} title={t("filters.clear")} disabled={busy} onClick={() => void leaveFacts(() => { onSearchChange(""); onRoleFilterChange("all"); onImportanceFilterChange("all"); })}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
            </label>
            <label className="grid gap-1.5 text-xs font-medium text-muted">
              <span>{t("filters.roleType")}</span>
              <select disabled={busy} value={roleFilter} onChange={(event) => { const value = event.target.value as "all" | CharacterRoleType; void leaveFacts(() => onRoleFilterChange(value)); }} className={FILTER_CLASS}>
                <option value="all">{t("filters.allRoleTypes")}</option>
                {ROLE_TYPES.map((item) => <option key={item} value={item}>{t(`options.roleType.${item}`)}</option>)}
              </select>
            </label>
            <label className="grid gap-1.5 text-xs font-medium text-muted">
              <span>{t("filters.importanceLevel")}</span>
              <select disabled={busy} value={importanceFilter} onChange={(event) => { const value = event.target.value as "all" | CharacterImportanceLevel; void leaveFacts(() => onImportanceFilterChange(value)); }} className={FILTER_CLASS}>
                <option value="all">{t("filters.allImportanceLevels")}</option>
                {IMPORTANCE_LEVELS.map((item) => <option key={item} value={item}>{t(`options.importanceLevel.${item}`)}</option>)}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onPress={onManualCreate} isDisabled={loading || busy}>{t("manualCreateCharacter")}</Button>
            <Button variant="primary" size="sm" onPress={onGenerate} isDisabled={loading || busy || generationLocked}>{generationLocked ? t("generating") : t("generateCharacters")}</Button>
          </div>
        </div>
      </section>

      {loading && allCharacterCount === 0 ? <LoadingPanel label={t("loading")} /> : !selected ? (
        <EmptyPanel title={filtersActive ? t("filters.noResults") : t("emptyCharacters")} />
      ) : (
        <>
        {noResults && <EmptyPanel title={t("filters.noResults")} />}
        {/* 搜索暂时无结果时只隐藏详情，避免卸载其中未保存的章节草稿。 */}
        <div inert={noResults} aria-hidden={noResults || undefined} className={`${noResults ? "hidden" : "grid"} min-h-[500px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
          <div className={`${mobileDetailOpen || listCollapsed ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
          <aside
            data-entity-roster id="character-profile-list"
            inert={listCollapsed}
            aria-hidden={listCollapsed || undefined}
            className={`${listCollapsed ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`}
            aria-label={t("tabs.profiles")}
            tabIndex={0}
          >
            <ul className="divide-y divide-border">
              {characters.map((character) => (
                <li key={character.character_id}>
                  <button id={`character-roster-${character.character_id}`} aria-current={selected.character_id === character.character_id ? "true" : undefined} type="button" disabled={busy} onClick={() => void leaveFacts(() => {
                    setSelectedId(character.character_id);
                    setMobileDetailOpen(true);
                    requestAnimationFrame(() => {
                      const detail = document.getElementById(`character-detail-${character.character_id}`);
                      if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                        detail.focus();
                      }
                    });
                  })} className={`w-full px-4 py-3 text-left transition-colors ${selected?.character_id === character.character_id ? "bg-selected border-l-2 border-accent" : "hover:bg-surface-secondary/55"}`}>
                    <span className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm font-semibold text-foreground">{character.name || t("card.untitled")}</span>
                      <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${character.status === "active" ? "bg-emerald-500" : "bg-muted/45"}`} />
                    </span>
                    <span className="mt-1 block truncate text-xs text-muted">{t(`options.roleType.${character.role_type}`)} · {t(`options.importanceLevel.${character.importance_level}`)} · {character.status === "active" ? t("status.active") : t("status.inactive")}</span>
                    <span className="mt-2 block text-xs tabular-nums text-muted">{t("relationCount", { count: relationCountByCharacter.get(character.character_id) ?? 0 })}</span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <SidebarEdgeHandle controls="character-profile-list" className="hidden @min-[800px]/master:flex"
            leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => { setListCollapsed(true); setMobileDetailOpen(true); } }}
            rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => { if (!busy) void leaveFacts(() => { setListCollapsed(false); setMobileDetailOpen(false); }); } } : undefined}
          />
          </div>
          <div
            id={`character-detail-${selected.character_id}`}
            className={`@container/detail ${mobileDetailOpen || listCollapsed ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0 @min-[800px]/master:overflow-y-auto`}
            role="region"
            aria-label={`${t("tabs.profiles")} · ${selected.name}`}
            tabIndex={0}
          >
            <button type="button" disabled={busy} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => void leaveFacts(() => {
              const characterId = selected.character_id;
              setListCollapsed(false);
              setMobileDetailOpen(false);
              requestAnimationFrame(() => document.getElementById(`character-roster-${characterId}`)?.focus());
            })}>← {t("actions.backToRoster")}</button>
            <CharacterDetail character={selected} busy={saving || factsBusy || actionId.includes(selected.character_id)} leavingFacts={leavingFacts} onSave={onSave} onToggleStatus={() => void leaveFacts(() => onToggleStatus(selected))} onDelete={() => void leaveFacts(() => onDelete(selected))} onFactsChanged={onFactsChanged} onFactsBusy={setFactsBusy} factsBeforeLeaveRef={factsBeforeLeaveRef} t={t} />
          </div>
        </div>
        </>
      )}
    </div>
  );
}

/**
 * 功能：渲染关系边清单与单一关系详情组成的主从工作台。
 * Args:
 *   props: 已保存关系、两端名称、生成状态与关系操作回调。
 * Returns:
 *   关系清单和详情编辑入口组成的响应式 React 节点。
 */
export function RelationsView({
  relations,
  activeCharacters,
  coreCharacters,
  characterNames,
  loading,
  generationLocked,
  actionId,
  onManualCreate,
  onGenerate,
  onRelationChanged,
  onFactsChanged,
  onBusyChange,
  beforeLeaveRef,
  saving,
  onCopy,
  onToggleActive,
  onDelete,
  t,
}: RelationsViewProps) {
  const listT = useTranslations("writing.listLayout");
  const active = useContext(RetainedViewActive);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [relationSearch, setRelationSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [factsBusy, setFactsBusy] = useState(false);
  const [designBusy, setDesignBusy] = useState(false);
  const [leavingFacts, setLeavingFacts] = useState(false);
  const [leaveError, setLeaveError] = useState("");
  const factsBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const leaveRequest = useRef(0);
  const alive = useRef(true);
  const names = (relation: CharacterRelationResponseV1) => ({
    source: relation.source_character_name || characterNames.get(relation.source_character_id) || "—",
    target: relation.target_character_name || characterNames.get(relation.target_character_id) || "—",
  });
  const relationQuery = relationSearch.trim().toLocaleLowerCase();
  const filteredRelations = relations.filter((relation) => {
    if (!relationQuery) return true;
    const relationNames = names(relation);
    return [
      relationNames.source,
      relation.source_character_id,
      relationNames.target,
      relation.target_character_id,
      t(`options.relationType.${relation.relation_type}`),
    ].some((value) => value.toLocaleLowerCase().includes(relationQuery));
  });
  const selected = filteredRelations.find((item) => item.relation_id === selectedId) ?? filteredRelations[0]
    ?? relations.find((item) => item.relation_id === selectedId) ?? relations[0];
  const context = useRef({ active, relationId: selected?.relation_id }); context.current = { active, relationId: selected?.relation_id };
  const busy = saving || factsBusy || designBusy || leavingFacts;
  useEffect(() => { alive.current = true; return () => { alive.current = false; leaveRequest.current += 1; }; }, []);
  useEffect(() => { if (!active) { leaveRequest.current += 1; setLeavingFacts(false); } }, [active]);
  useEffect(() => { if (!selectedId && selected) setSelectedId(selected.relation_id); }, [selectedId, selected]);
  useEffect(() => { onBusyChange?.(factsBusy || designBusy || leavingFacts); return () => onBusyChange?.(false); }, [factsBusy, designBusy, leavingFacts, onBusyChange]);
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (saving || factsBusy || designBusy || leavingFacts) throw new Error(t("actions.saving")); await factsBeforeLeaveRef.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  }, [beforeLeaveRef, saving, factsBusy, designBusy, leavingFacts, t]);
  const leaveFacts = async (change: () => void) => {
    if (saving || factsBusy || designBusy) return;
    const request = ++leaveRequest.current;
    const relationId = selected?.relation_id;
    setLeavingFacts(true); setLeaveError("");
    try {
      await factsBeforeLeaveRef.current?.();
      if (alive.current && request === leaveRequest.current && context.current.active && context.current.relationId === relationId) change();
    } catch (failure) {
      if (alive.current && request === leaveRequest.current) { setLeaveError(failure instanceof Error ? failure.message : String(failure)); setSearchInput(relationSearch); }
    } finally { if (alive.current && request === leaveRequest.current) setLeavingFacts(false); }
  };
  useAssistantFocus("character_relation", (target) => { if (busy || !relations.some((relation) => relation.relation_id === target.id)) return false; void leaveFacts(() => { setSelectedId(target.id); setRelationSearch(""); setSearchInput(""); setMobileDetailOpen(true); }); });
  const noResults = filteredRelations.length === 0 && relations.length > 0;
  const insufficientActiveCharacters = activeCharacters.length < 2;
  const insufficientCoreCharacters = coreCharacters.length < 2;

  // 与角色档案共用同一滚动边界，详情滚动不会带动左侧关系边清单。
  return (
    <div
      id={`${CHARACTER_WORKSPACE_TAB_PREFIX}-relations-panel`}
      role="tabpanel"
      aria-labelledby={`${CHARACTER_WORKSPACE_TAB_PREFIX}-relations-tab`}
      className="@container/master flex h-full min-h-0 flex-col gap-3"
    >
      {leaveError && <RelationEditorErrorSummary message={leaveError} />}
      <section className={`shrink-0 border-b border-border pb-3 ${mobileDetailOpen && !noResults ? "hidden @min-[800px]/master:block" : ""}`}>
        <div className="workspace-toolbar flex flex-wrap items-end gap-3">
          <label className="grid min-w-0 flex-[1_1_20rem] gap-1.5 text-xs font-medium text-muted">
            <span>{t("filters.relationSearchLabel")}</span>
            <span className="relative block min-w-0"><input type="search" aria-label={t("filters.relationSearchLabel")} disabled={saving || factsBusy || designBusy} value={searchInput} onChange={(event) => { const value = event.target.value; setSearchInput(value); void leaveFacts(() => setRelationSearch(value)); }} placeholder={t("filters.relationSearchPlaceholder")} className={`${FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`} />{Boolean(relationSearch) && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("filters.clear")} title={t("filters.clear")} disabled={busy} onClick={() => void leaveFacts(() => { setRelationSearch(""); setSearchInput(""); })}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onPress={onManualCreate} isDisabled={loading || busy || insufficientActiveCharacters}>{t("manualCreateRelation")}</Button>
            <Button variant="primary" size="sm" onPress={() => void leaveFacts(onGenerate)} isDisabled={loading || busy || generationLocked || insufficientCoreCharacters}>{generationLocked ? t("generating") : t("generateRelations")}</Button>
          </div>
        </div>
        {insufficientCoreCharacters && <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">{t("needTwoCoreCharacters")}</p>}
      </section>

      {loading && relations.length === 0 ? <LoadingPanel label={t("loading")} /> : relations.length === 0 ? (
        <EmptyPanel title={t("emptyRelations")} />
      ) : !selected ? (
        <EmptyPanel title={t("filters.noRelationResults")} />
      ) : (
        <>
        {noResults && <EmptyPanel title={t("filters.noRelationResults")} />}
        <div inert={noResults} aria-hidden={noResults || undefined} className={`${noResults ? "hidden" : "grid"} min-h-[500px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
          <div className={`${mobileDetailOpen || listCollapsed ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
          <aside
            id="character-relation-list"
            inert={listCollapsed}
            aria-hidden={listCollapsed || undefined}
            className={`${listCollapsed ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`}
            aria-label={t("tabs.relations")}
            tabIndex={0}
          >
            <ul className="divide-y divide-border">
              {filteredRelations.map((relation) => {
                const relationNames = names(relation);
                const symmetric = isSymmetricCharacterRelation(relation.relation_type);
                const connector = symmetric ? "↔" : "→";
                return (
                  <li key={relation.relation_id}>
                    <button id={`character-relation-roster-${relation.relation_id}`} aria-current={selected.relation_id === relation.relation_id ? "true" : undefined} type="button" disabled={busy} onClick={() => void leaveFacts(() => {
                      setSelectedId(relation.relation_id);
                      setMobileDetailOpen(true);
                      requestAnimationFrame(() => {
                        const detail = document.getElementById(`character-relation-detail-${relation.relation_id}`);
                        if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                          detail.focus();
                        }
                      });
                    })} className={`w-full px-4 py-3 text-left transition-colors ${selected.relation_id === relation.relation_id ? "bg-selected border-l-2 border-accent" : "hover:bg-surface-secondary/55"}`}>
                      <span className="block truncate text-sm font-semibold text-foreground">{relationNames.source} <span className="text-accent">{connector}</span> {relationNames.target}</span>
                      <span className="mt-1 block text-xs text-muted">{t(`options.relationType.${relation.relation_type}`)} · {t(`relationDirection.${symmetric ? "symmetric" : "directed"}`)} · {relation.intensity}/5</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>
          <SidebarEdgeHandle controls="character-relation-list" className="hidden @min-[800px]/master:flex"
            leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => { setListCollapsed(true); setMobileDetailOpen(true); } }}
            rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => { if (!busy) void leaveFacts(() => { setListCollapsed(false); setMobileDetailOpen(false); }); } } : undefined}
          />
          </div>
          <div
            id={`character-relation-detail-${selected.relation_id}`}
            className={`@container/detail ${mobileDetailOpen || listCollapsed ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0 @min-[800px]/master:overflow-y-auto`}
            role="region"
            aria-label={`${t("tabs.relations")} · ${names(selected).source} ${isSymmetricCharacterRelation(selected.relation_type) ? "↔" : "→"} ${names(selected).target}`}
            tabIndex={0}
          >
            <button type="button" disabled={busy} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => void leaveFacts(() => {
              const relationId = selected.relation_id;
              setListCollapsed(false);
              setMobileDetailOpen(false);
              requestAnimationFrame(() => document.getElementById(`character-relation-roster-${relationId}`)?.focus());
            })}>← {t("actions.backToRoster")}</button>
            <RelationDetail relation={selected} names={names(selected)} busy={busy || actionId.includes(selected.relation_id)} designReadOnly={saving || factsBusy || leavingFacts || actionId.includes(selected.relation_id)} factsReadOnly={saving || designBusy || leavingFacts || actionId.includes(selected.relation_id)} onRelationChanged={onRelationChanged} onFactsChanged={onFactsChanged} onFactsBusy={setFactsBusy} onDesignBusy={setDesignBusy} factsBeforeLeaveRef={factsBeforeLeaveRef} onCopy={() => onCopy(selected)} onToggleActive={() => void leaveFacts(() => onToggleActive(selected))} onDelete={() => void leaveFacts(() => onDelete(selected))} t={t} />
          </div>
        </div>
        </>
      )}
    </div>
  );
}

/**
 * 功能：按角色展示主归属、次要归属、隐秘归属及历史绑定。
 * Args:
 *   props: 角色、绑定、核心势力、动作状态及绑定生命周期回调。
 * Returns:
 *   移动端列表到详情、桌面端双栏且独立滚动的绑定工作台。
 */
export function BindingsView({
  characters,
  bindings,
  factions,
  loading,
  actionId,
  saving,
  editingBindingId,
  editor,
  onCreate,
  onEdit,
  onToggleActive,
  onMakePrimary,
  onDelete,
  onRestore,
  onHardDelete,
  t,
}: BindingsViewProps) {
  const listT = useTranslations("writing.listLayout");
  const [listCollapsed, setListCollapsed] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [characterSearch, setCharacterSearch] = useState("");
  const query = characterSearch.trim().toLocaleLowerCase();
  const filteredCharacters = characters.filter((character) =>
    !query || [character.name, character.character_id, ...character.aliases]
      .some((value) => value.toLocaleLowerCase().includes(query)),
  );
  const selected = filteredCharacters.find((character) => character.character_id === selectedId) ?? filteredCharacters[0];
  const [focusedBinding, setFocusedBinding] = useState("");
  useEffect(() => {
    if (!focusedBinding) return;
    const frame = requestAnimationFrame(() => {
      const row = document.getElementById(`character-binding-row-${focusedBinding}`);
      row?.scrollIntoView({ block: "nearest" }); row?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusedBinding]);
  useAssistantFocus("character_faction_binding", (target) => { const binding = bindings.find((item) => item.binding_id === target.id); if (binding) { setSelectedId(binding.character_id); setCharacterSearch(""); setMobileDetailOpen(true); setFocusedBinding(target.id); return true; } return false; });
  const bindingResource = bindings.find((item) => item.binding_id === (editingBindingId || focusedBinding));
  useAssistantResource(bindingResource ? { resource_type: "character_faction_binding", id: bindingResource.binding_id, name: bindingResource.binding_id, version: bindingResource.version } : null);
  const selectedBindings = selected
    ? bindings.filter((binding) => binding.character_id === selected.character_id)
    : [];
  const activeFactions = factions.filter((faction) =>
    !faction.is_deleted && (faction.active_status ?? "active") === "active" && (faction.level_type ?? "core") === "core",
  );
  const factionNames = new Map(factions.map((faction) => [faction.faction_id, faction.name]));
  const groups = selected ? [
    {
      key: "primary",
      label: t("binding.groups.primary"),
      items: selectedBindings.filter((binding) => !binding.is_deleted && binding.is_active && binding.membership_type === "primary"),
    },
    {
      key: "secondary",
      label: t("binding.groups.secondary"),
      items: selectedBindings.filter((binding) => !binding.is_deleted && binding.is_active && binding.membership_type === "secondary"),
    },
    {
      key: "covert",
      label: t("binding.groups.covert"),
      items: selectedBindings.filter((binding) => !binding.is_deleted && binding.is_active && binding.membership_type === "covert"),
    },
    {
      key: "history",
      label: t("binding.groups.history"),
      items: selectedBindings.filter((binding) => binding.is_deleted || !binding.is_active),
    },
  ] : [];
  const canCreate = Boolean(
    selected &&
    !selected.is_deleted &&
    selected.status === "active" &&
    selected.is_core_character &&
    activeFactions.length > 0,
  );

  return (
    <div
      id={`${CHARACTER_WORKSPACE_TAB_PREFIX}-bindings-panel`}
      role="tabpanel"
      aria-labelledby={`${CHARACTER_WORKSPACE_TAB_PREFIX}-bindings-tab`}
      className="@container/master flex h-full min-h-0 flex-col gap-3"
    >
      <section className={`shrink-0 border-b border-border pb-3 ${mobileDetailOpen ? "hidden @min-[800px]/master:block" : ""}`}>
        <label className="grid gap-1.5 text-xs font-medium text-muted">
          <span>{t("binding.searchLabel")}</span>
          <span className="relative block min-w-0"><input type="search" aria-label={t("binding.searchLabel")} disabled={saving} value={characterSearch} onChange={(event) => setCharacterSearch(event.target.value)} placeholder={t("binding.searchPlaceholder")} className={`${FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`} />{Boolean(characterSearch) && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("filters.clear")} title={t("filters.clear")} disabled={saving} onClick={() => setCharacterSearch("")}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
        </label>
      </section>

      {loading && characters.length === 0 ? <LoadingPanel label={t("loading")} /> : !selected ? (
        <EmptyPanel title={query ? t("filters.noResults") : t("emptyCharacters")} />
      ) : (
        <div className={`grid min-h-[500px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
          <div className={`${mobileDetailOpen || listCollapsed ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
          <aside
            id="character-binding-list"
            inert={listCollapsed}
            aria-hidden={listCollapsed || undefined}
            className={`${listCollapsed ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`}
            aria-label={t("binding.characterRoster")}
            tabIndex={0}
          >
            <ul className="divide-y divide-border">
              {filteredCharacters.map((character) => {
                const count = bindings.filter((binding) => binding.character_id === character.character_id).length;
                return (
                  <li key={character.character_id}>
                    <button
                      id={`character-binding-roster-${character.character_id}`}
                      aria-current={selected.character_id === character.character_id ? "true" : undefined}
                      type="button"
                      disabled={saving}
                      onClick={() => {
                        setSelectedId(character.character_id);
                        setMobileDetailOpen(true);
                        requestAnimationFrame(() => {
                          const detail = document.getElementById(`character-binding-detail-${character.character_id}`);
                          if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                            detail.focus();
                          }
                        });
                      }}
                      className={`w-full px-4 py-3 text-left transition-colors ${selected.character_id === character.character_id ? "bg-selected border-l-2 border-accent" : "hover:bg-surface-secondary/55"}`}
                    >
                      <span className="block truncate text-sm font-semibold text-foreground">{character.name}</span>
                      <span className="mt-2 block text-xs text-muted">{t("binding.count", { count })}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>
          <SidebarEdgeHandle controls="character-binding-list" className="hidden @min-[800px]/master:flex"
            leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => { setListCollapsed(true); setMobileDetailOpen(true); } }}
            rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => { setListCollapsed(false); setMobileDetailOpen(false); } } : undefined}
          />
          </div>
          <div
            id={`character-binding-detail-${selected.character_id}`}
            className={`@container/detail ${mobileDetailOpen || listCollapsed ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0`}
            role="region"
            aria-label={`${t("tabs.bindings")} · ${selected.name}`}
            tabIndex={0}
          >
            <button type="button" disabled={saving} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
              const characterId = selected.character_id;
              setListCollapsed(false);
              setMobileDetailOpen(false);
              requestAnimationFrame(() => document.getElementById(`character-binding-roster-${characterId}`)?.focus());
            }}>← {t("actions.backToRoster")}</button>
            <header className="flex flex-col gap-4 border-b border-border px-5 py-4 @[640px]/detail:flex-row @[640px]/detail:items-start @[640px]/detail:justify-between sm:px-7">
              <div className="min-w-0">
                <h2 className="sr-only">{selected.name}</h2>
                <p className="mt-1 font-mono text-xs text-muted">{selected.character_id}</p>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onPress={() => onCreate(selected)} isDisabled={saving || Boolean(editingBindingId) || !canCreate}>{t("binding.create")}</Button>
                {!canCreate && <TooltipHint text={activeFactions.length === 0 ? t("binding.noFactionTooltip") : t("binding.characterUnavailableTooltip")} />}
              </div>
            </header>
            <div className="space-y-4 px-5 py-4 sm:px-7">
              {groups.map((group, index) => (
                <DocumentSection key={group.key} number={String(index + 1).padStart(2, "0")} title={group.label} actions={group.key === "primary" && group.items.filter((binding) => binding.binding_id !== editingBindingId).map((binding) => (
                  <SectionEditButton key={binding.binding_id} type="button" id={`character-binding-edit-${binding.binding_id}`} onPress={() => onEdit(binding)} isDisabled={saving || actionId.includes(binding.binding_id) || Boolean(editingBindingId)} label={t("actions.edit")} />
                ))}>
                  {group.items.length === 0 ? (
                    <p className="mt-3 text-sm text-muted">{t("binding.groupEmpty")}</p>
                  ) : (
                    <div className="mt-3 divide-y divide-border">
                      {group.items.map((binding) => (
                        <BindingRow
                          key={binding.binding_id}
                          binding={binding}
                          factionName={factionNames.get(binding.faction_id) ?? binding.faction_id}
                          busy={saving || actionId.includes(binding.binding_id) || Boolean(editingBindingId)}
                          editor={editingBindingId === binding.binding_id ? editor : undefined}
                          onEdit={() => onEdit(binding)}
                          onToggleActive={() => onToggleActive(binding)}
                          onMakePrimary={() => onMakePrimary(binding)}
                          onDelete={() => onDelete(binding)}
                          onRestore={() => onRestore(binding)}
                          onHardDelete={() => onHardDelete(binding)}
                          t={t}
                        />
                      ))}
                    </div>
                  )}
                </DocumentSection>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** 渲染一条绑定事实及其当前可用生命周期动作。 */
function BindingRow({
  binding,
  factionName,
  busy,
  editor,
  onEdit,
  onToggleActive,
  onMakePrimary,
  onDelete,
  onRestore,
  onHardDelete,
  t,
}: {
  binding: CharacterFactionBindingResponseV1;
  factionName: string;
  busy: boolean;
  editor?: ReactNode;
  onEdit: () => void;
  onToggleActive: () => void;
  onMakePrimary: () => void;
  onDelete: () => void;
  onRestore: () => void;
  onHardDelete: () => void;
  t: CharactersTranslator;
}) {
  const endpointBlocked = binding.disabled_by_character_ids.length > 0 || binding.disabled_by_faction_ids.length > 0;
  const statusKey = binding.is_deleted
    ? "deleted"
    : !binding.user_is_active
      ? "userInactive"
      : endpointBlocked
        ? "endpointBlocked"
        : "active";
  return (
    <article id={`character-binding-row-${binding.binding_id}`} tabIndex={-1} className="space-y-3 py-3 first:pt-0 last:pb-0 focus-visible:outline-2 focus-visible:outline-accent">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="min-w-0 text-sm font-semibold text-foreground [overflow-wrap:anywhere]">{factionName}</h4>
          {!editor && !binding.is_deleted && (!binding.is_active || binding.membership_type !== "primary") && <SectionEditButton key="edit" type="button" id={`character-binding-edit-${binding.binding_id}`} onPress={onEdit} isDisabled={busy} label={t("actions.edit")} />}
          <StatusPill active={binding.is_active && !binding.is_deleted}>{t(`binding.status.${statusKey}`)}</StatusPill>
          {endpointBlocked && <TooltipHint text={t("binding.blockedTooltip", { characters: binding.disabled_by_character_ids.join(", ") || "—", factions: binding.disabled_by_faction_ids.join(", ") || "—" })} />}
        </div>
        <p className="mt-1 text-xs text-muted">{t(`options.membershipType.${binding.membership_type}`)}{binding.role_title ? ` · ${binding.role_title}` : ""}</p>
        <p className="mt-1 font-mono text-xs text-muted">{binding.faction_id} · {binding.binding_id}</p>
      </div>
      {!editor && <div className="flex shrink-0 flex-wrap gap-2">
        {binding.is_deleted ? (
          <>
            <Button size="sm" variant="outline" onPress={onRestore} isDisabled={busy}>{t("actions.restore")}</Button>
            <Button size="sm" variant="ghost" className="text-danger" onPress={onHardDelete} isDisabled={busy}>{t("actions.hardDelete")}</Button>
          </>
        ) : (
          <>
            {binding.membership_type !== "primary" && <Button size="sm" variant="ghost" onPress={onMakePrimary} isDisabled={busy || endpointBlocked}>{t("binding.makePrimary")}</Button>}
            <SectionActionButton action={binding.user_is_active ? "deactivate" : "activate"} label={t(binding.user_is_active ? "actions.deactivate" : "actions.activate")} onPress={onToggleActive} isDisabled={busy} />
            <SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" onPress={onDelete} isDisabled={busy} />
          </>
        )}
      </div>}
      </div>
      {editor ?? <dl className="detail-fields grid min-w-0 gap-4">
        <ReadOnlyField label={t("binding.publicStatus")} value={binding.public_status || "—"} />
        <ReadOnlyField label={t("binding.loyaltyLevel")} value={binding.loyalty_level ?? "—"} />
        <ReadOnlyField wide label={t("binding.notes")} value={binding.notes || "—"} />
      </dl>}
    </article>
  );
}

/**
 * 功能：渲染角色与人物关系回收站，并只在此处暴露永久删除。
 * Args:
 *   props: 已软删实体、当前动作标识以及恢复和永久删除回调。
 * Returns:
 *   按角色和关系分区展示的回收站 React 节点。
 */
export function TrashView({ characters, relations, actionId, onRestoreCharacter, onHardDeleteCharacter, onRestoreRelation, onHardDeleteRelation, t }: TrashViewProps) {
  return (
    <div
      id={`${CHARACTER_WORKSPACE_TAB_PREFIX}-trash-panel`}
      role="tabpanel"
      aria-labelledby={`${CHARACTER_WORKSPACE_TAB_PREFIX}-trash-tab`}
      className="space-y-8"
    >
      <TrashSection title={t("trash.characters")} empty={characters.length === 0} emptyText={t("trash.emptyCharacters")}>
        {characters.map((character) => (
          <TrashRow key={character.character_id} title={character.name} meta={character.character_id} busy={actionId.includes(character.character_id)} onRestore={() => onRestoreCharacter(character)} onHardDelete={() => onHardDeleteCharacter(character)} t={t} />
        ))}
      </TrashSection>
      <TrashSection title={t("trash.relations")} empty={relations.length === 0} emptyText={t("trash.emptyRelations")}>
        {relations.map((relation) => {
          const connector = isSymmetricCharacterRelation(relation.relation_type) ? "↔" : "→";
          return <TrashRow key={relation.relation_id} title={`${relation.source_character_name || relation.source_character_id} ${connector} ${relation.target_character_name || relation.target_character_id}`} meta={relation.relation_id} busy={actionId.includes(relation.relation_id)} onRestore={() => onRestoreRelation(relation)} onHardDelete={() => onHardDeleteRelation(relation)} t={t} />;
        })}
      </TrashSection>
    </div>
  );
}

/**
 * 功能：渲染 HeroUI v3 模态容器，统一焦点圈定、Escape、滚动锁和焦点恢复。
 * Args:
 *   props: 弹窗标题、说明、正文、底部动作、关闭回调、可关闭策略与保存状态。
 * Returns:
 *   移动端近全屏、桌面端限高的统一模态 React 节点。
 */
export function ModalLayer({ title, description, onClose, footer, children, dismissable = true, busy = false }: ModalLayerProps) {
  return (
      <RetainedModalBackdrop
        isOpen
        onOpenChange={(isOpen) => !isOpen && !busy && onClose()}
        variant="blur"
        isDismissable={dismissable && !busy}
        isKeyboardDismissDisabled={busy}
      >
        <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
          <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-5xl">
            <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-6">
              <div>
                <Modal.Heading className="text-lg font-semibold text-foreground">{title}</Modal.Heading>
                {description && <p className="mt-1 text-sm leading-6 text-muted">{description}</p>}
              </div>
              <Modal.CloseTrigger aria-label={title} isDisabled={busy} />
            </Modal.Header>
            <Modal.Body className="min-h-0 px-5 py-5 sm:px-6">{children}</Modal.Body>
            <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-6">{footer}</Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </RetainedModalBackdrop>
  );
}

function CharacterDetail({ character, busy, leavingFacts, onSave, onToggleStatus, onDelete, onFactsChanged, onFactsBusy, factsBeforeLeaveRef, t }: { character: CharacterResponseV1; busy: boolean; leavingFacts: boolean; onSave: ProfilesViewProps["onSave"]; onToggleStatus: () => void; onDelete: () => void; onFactsChanged?: ProfilesViewProps["onFactsChanged"]; onFactsBusy: (busy: boolean) => void; factsBeforeLeaveRef: RefObject<(() => Promise<void>) | null>; t: CharactersTranslator }) {
  const [facts, setFacts] = useState<CharacterFactsAtPositionV1 | null>(null);
  const currentFacts = facts?.character_id === character.character_id ? facts : null;
  const hasLegacyProfileSection = currentFacts?.claimed_fields && ["appearance", "personality", "strengths", "weaknesses", "abilities"].some((field) => !currentFacts.claimed_fields.includes(field as CharacterFactField));
  return (
    <article data-entity-detail className="@container/detail min-w-0 px-5 py-4 sm:px-7">
      <header className="flex flex-col gap-4 @[640px]/detail:flex-row @[640px]/detail:items-start @[640px]/detail:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2"><StatusPill active={character.is_core_character}>{character.is_core_character ? t("status.core") : t("status.nonCore")}</StatusPill><StatusPill active={character.status === "active"}>{character.status === "active" ? t("status.active") : t("status.inactive")}</StatusPill></div>
          <h2 className="sr-only">{character.name}</h2>
          <p className="mt-1 font-mono text-xs text-muted">{character.character_id}</p>
        </div>
        {/* 离开草稿检查期间阻止重复操作并保留触发焦点，供确认框关闭时恢复。 */}
        <div className="flex flex-wrap gap-2">
          <SectionActionButton action={character.status === "active" ? "deactivate" : "activate"} label={t(character.status === "active" ? "actions.deactivate" : "actions.activate")} onPress={onToggleStatus} isDisabled={busy} isPending={leavingFacts} />
          <SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" onPress={onDelete} isDisabled={busy} isPending={leavingFacts} />
        </div>
      </header>
      <CharacterProfileSections claimedFactFields={currentFacts?.claimed_fields} character={character} busy={busy || leavingFacts} onSave={onSave} t={t} />
      <CharacterFactsPanel numberOffset={hasLegacyProfileSection ? 4 : 3} onRead={setFacts} novelId={character.novel_id} characterId={character.character_id} onChanged={onFactsChanged} readOnly={character.is_deleted} onBusy={onFactsBusy} beforeLeaveRef={factsBeforeLeaveRef} />
    </article>
  );
}

function RelationDetail({ relation, names, busy, designReadOnly, factsReadOnly, onRelationChanged, onFactsChanged, onFactsBusy, onDesignBusy, factsBeforeLeaveRef, onCopy, onToggleActive, onDelete, t }: { relation: CharacterRelationResponseV1; names: { source: string; target: string }; busy: boolean; designReadOnly: boolean; factsReadOnly: boolean; onRelationChanged?: RelationsViewProps["onRelationChanged"]; onFactsChanged?: RelationsViewProps["onFactsChanged"]; onFactsBusy: (busy: boolean) => void; onDesignBusy: (busy: boolean) => void; factsBeforeLeaveRef: RefObject<(() => Promise<void>) | null>; onCopy: () => void; onToggleActive: () => void; onDelete: () => void; t: CharactersTranslator }) {
  const symmetric = isSymmetricCharacterRelation(relation.relation_type);
  const connector = symmetric ? "↔" : "→";
  useAssistantResource({ resource_type: "character_relation", id: relation.relation_id, name: `${names.source} ${connector} ${names.target}`, version: relation.version });
  return (
    <article className="@container/detail min-w-0 px-5 py-4 sm:px-7">
      <header>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div><h2 className="sr-only">{names.source} {connector} {names.target}</h2><p className="font-mono text-xs text-muted">{relation.relation_id}</p><p className="mt-1 text-sm text-muted">{t(`relationDirection.${symmetric ? "symmetric" : "directed"}`)} · {relation.is_active ? t("status.active") : t("status.inactive")}</p></div>
          <div className="flex flex-wrap gap-2"><Button size="sm" variant="ghost" onPress={onCopy} isDisabled={busy}>{t("actions.copyAsNew")}</Button><SectionActionButton action={(relation.user_is_active ?? relation.is_active) ? "deactivate" : "activate"} label={t((relation.user_is_active ?? relation.is_active) ? "actions.deactivate" : "actions.activate")} onPress={onToggleActive} isDisabled={busy} /><SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" onPress={onDelete} isDisabled={busy} /></div>
        </div>
        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-secondary"><div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(0, Math.min(5, relation.intensity)) * 20}%` }} /></div>
      </header>
      <div className="mt-4 space-y-4">
        <CharacterRelationDesignSection relation={relation} readOnly={designReadOnly} onChanged={onRelationChanged} onBusy={onDesignBusy} />
        <CharacterRelationFactsPanel novelId={relation.novel_id} relation={relation} numberOffset={1} onChanged={onFactsChanged} readOnly={relation.is_deleted || factsReadOnly} onBusy={onFactsBusy} beforeLeaveRef={factsBeforeLeaveRef} />
      </div>
    </article>
  );
}

function TrashSection({ title, empty, emptyText, children }: { title: string; empty: boolean; emptyText: string; children: ReactNode }) {
  return <section><h2 className="border-b border-border pb-3 text-lg font-semibold text-foreground">{title}</h2>{empty ? <p className="py-8 text-sm text-muted">{emptyText}</p> : <div className="divide-y divide-border">{children}</div>}</section>;
}

function TrashRow({ title, meta, busy, onRestore, onHardDelete, t }: { title: string; meta: string; busy: boolean; onRestore: () => void; onHardDelete: () => void; t: CharactersTranslator }) {
  return <div className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><p className="truncate text-sm font-semibold text-foreground">{title}</p><p className="mt-1 truncate font-mono text-xs text-muted">{meta}</p></div><div className="flex gap-2"><Button size="sm" variant="outline" onPress={onRestore} isDisabled={busy}>{t("actions.restore")}</Button><Button size="sm" variant="ghost" className="text-danger" onPress={onHardDelete} isDisabled={busy}>{t("actions.hardDelete")}</Button></div></div>;
}

function StatusPill({ active, children }: { active: boolean; children: ReactNode }) {
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${active ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-surface-secondary text-muted"}`}>{children}</span>;
}

function EmptyPanel({ title, description }: { title: string; description?: string }) {
  return <div className="border-y border-dashed border-border px-5 py-14 text-center"><p className="text-sm font-medium text-foreground">{title}</p>{description && <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">{description}</p>}</div>;
}

function LoadingPanel({ label }: { label: string }) {
  return <div className="border-y border-border px-5 py-14 text-center" role="status"><span className="mx-auto block size-6 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" /><p className="mt-3 text-sm text-muted">{label}</p></div>;
}
