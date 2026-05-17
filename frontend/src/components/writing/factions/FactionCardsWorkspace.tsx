"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { apiDelete, apiGet, apiPost, apiPut } from "@/lib/api";
import type {
  BulkCreateCoreFactionsResponse,
  CoreFaction,
  CoreFactionsPayload,
  FactionRelation,
  FactionRelationType,
  GeneratedFactionRelation,
} from "@/types/novel";

interface FactionCardsWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
}

type FactionCategory = "core" | "volume" | "local" | "trash";
type EditorState = { mode: "create" | "edit"; draft: CoreFaction } | null;
type DeleteIntent = { mode: "soft" | "hard"; faction: CoreFaction } | null;

const RELATION_TYPES: FactionRelationType[] = [
  "hostile",
  "allied",
  "cold_war",
  "dependent",
  "subordinate",
  "trade_partner",
  "secret_cooperation",
  "historical_enemy",
];

const ARRAY_SEPARATOR = /\n|,|，|、|;|；/;
const CORE_FACTION_WARNING_COUNT = 6;

/**
 * 将多行或顿号分隔文本归一化为字符串数组。
 *
 * Args:
 *   value: 用户在 textarea 中输入的列表文本。
 *
 * Returns:
 *   去掉空项后的字符串数组。
 */
function splitListText(value: string): string[] {
  return value
    .split(ARRAY_SEPARATOR)
    .map((item) => item.trim())
    .filter(Boolean);
}

/**
 * 将数组字段格式化为多行文本，便于在 textarea 中编辑。
 *
 * Args:
 *   value: 需要展示的字符串数组。
 *
 * Returns:
 *   多行文本。
 */
function joinListText(value: string[] | undefined): string {
  return (value ?? []).join("\n");
}

/**
 * 归一化 AI 生成结果，补齐前端编辑所需默认值。
 *
 * Args:
 *   payload: 后端返回的核心阵营与关系预览。
 *
 * Returns:
 *   可直接进入前端编辑状态的预览数据。
 */
function normalizeGeneratedPayload(payload: CoreFactionsPayload): CoreFactionsPayload {
  return {
    core_factions: payload.core_factions.map((faction, index) =>
      createFactionDraft(faction, index),
    ),
    faction_relations: payload.faction_relations.map((relation) => ({
      ...relation,
      hidden_tension: relation.hidden_tension ?? "",
      intensity: relation.intensity ?? 3,
      is_active: relation.is_active ?? true,
    })),
  };
}

/**
 * 生成可编辑的核心阵营草稿。
 *
 * Args:
 *   source: 可选的已有阵营数据。
 *   index: 草稿排序位置。
 *
 * Returns:
 *   字段齐全的核心阵营草稿。
 */
function createFactionDraft(source: Partial<CoreFaction> = {}, index = 0): CoreFaction {
  return {
    _id: source._id,
    novel_id: source.novel_id,
    faction_id: source.faction_id,
    name: source.name ?? "",
    alias: source.alias ?? [],
    faction_type: source.faction_type ?? "",
    level_type: source.level_type ?? "core",
    parent_faction_id: source.parent_faction_id ?? null,
    positioning: source.positioning ?? "",
    public_stance: source.public_stance ?? "",
    core_goal: source.core_goal ?? "",
    hidden_goal: source.hidden_goal ?? "",
    resources_and_advantages: source.resources_and_advantages ?? [],
    organization_style: source.organization_style ?? "",
    core_values: source.core_values ?? [],
    conflict_with_mainline: source.conflict_with_mainline ?? "",
    is_public: source.is_public ?? true,
    influence_scope: source.influence_scope ?? "",
    active_status: source.active_status ?? "active",
    expandability: source.expandability ?? "",
    tags: source.tags ?? [],
    sort_order: source.sort_order ?? (index + 1) * 10,
  };
}

/**
 * 提取阵营写入 API 支持的字段。
 *
 * Args:
 *   draft: 前端编辑中的阵营草稿。
 *
 * Returns:
 *   可提交给创建或更新接口的阵营字段。
 */
function buildFactionRequest(draft: CoreFaction): Partial<CoreFaction> {
  return {
    name: draft.name.trim(),
    alias: draft.alias ?? [],
    faction_type: draft.faction_type.trim(),
    level_type: draft.level_type ?? "core",
    parent_faction_id: draft.parent_faction_id ?? null,
    positioning: draft.positioning.trim(),
    public_stance: draft.public_stance.trim(),
    core_goal: draft.core_goal.trim(),
    hidden_goal: draft.hidden_goal?.trim() ?? "",
    resources_and_advantages: draft.resources_and_advantages ?? [],
    organization_style: draft.organization_style.trim(),
    core_values: draft.core_values ?? [],
    conflict_with_mainline: draft.conflict_with_mainline.trim(),
    is_public: draft.is_public,
    influence_scope: draft.influence_scope.trim(),
    active_status: draft.active_status ?? "active",
    expandability: draft.expandability.trim(),
    tags: draft.tags ?? [],
    sort_order: draft.sort_order ?? 0,
  };
}

/**
 * Resolve the stable frontend identity for a saved core faction.
 *
 * Args:
 *   faction: A faction returned by the API or held in local state.
 *
 * Returns:
 *   The business id when available, then Mongo id, then the faction name.
 */
function getFactionRenderKey(faction: CoreFaction): string {
  return faction.faction_id || faction._id || faction.name;
}

/**
 * Resolve the stable frontend identity for a saved faction relation.
 *
 * Args:
 *   relation: A relation returned by the API or held in local state.
 *
 * Returns:
 *   The business id when available, then Mongo id, then a relation endpoint signature.
 */
function getRelationRenderKey(relation: FactionRelation): string {
  return (
    relation.relation_id ||
    relation._id ||
    `${relation.source_faction_id ?? relation.source_faction_name ?? ""}->${relation.target_faction_id ?? relation.target_faction_name ?? ""}:${relation.relation_type}`
  );
}

/**
 * Merge incoming API rows into current state without duplicating React keys.
 *
 * Args:
 *   current: Rows already rendered in the workspace.
 *   incoming: Fresh rows returned by save or reload APIs.
 *   getKey: Stable identity resolver for each row.
 *
 * Returns:
 *   A list where later rows replace earlier rows with the same key.
 */
function mergeUniqueByKey<T>(current: T[], incoming: T[], getKey: (item: T) => string): T[] {
  const rowsByKey = new Map<string, T>();

  // 保存响应和刷新请求可能交错返回，统一按业务 ID 覆盖旧行，避免同一条记录被追加两次。
  for (const item of [...current, ...incoming]) {
    rowsByKey.set(getKey(item), item);
  }

  return Array.from(rowsByKey.values());
}

/**
 * 渲染已保存小说的势力卡工作台，并承接核心阵营生成、编辑与垃圾桶操作。
 *
 * Args:
 *   mode: 写作页当前模式，只有 edit 模式允许读取和写入已保存小说。
 *   novelId: 已保存小说的 ObjectId 字符串。
 *
 * Returns:
 *   势力卡模块 React 节点。
 */
export default function FactionCardsWorkspace({ mode, novelId }: FactionCardsWorkspaceProps) {
  const t = useTranslations("writing.factions");
  const [activeCategory, setActiveCategory] = useState<FactionCategory>("core");
  const [factions, setFactions] = useState<CoreFaction[]>([]);
  const [trashFactions, setTrashFactions] = useState<CoreFaction[]>([]);
  const [relations, setRelations] = useState<FactionRelation[]>([]);
  const [preview, setPreview] = useState<CoreFactionsPayload | null>(null);
  const [editor, setEditor] = useState<EditorState>(null);
  const [deleteIntent, setDeleteIntent] = useState<DeleteIntent>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actionId, setActionId] = useState("");
  const [error, setError] = useState("");

  const canUseSavedNovel = mode === "edit" && Boolean(novelId);
  const hasAnyCoreRecord = factions.length + trashFactions.length > 0;
  const shouldWarnTooManyCoreFactions = factions.length >= CORE_FACTION_WARNING_COUNT;
  const canGenerateCoreFactions = !hasAnyCoreRecord && !preview;

  const relationTypeLabels: Record<FactionRelationType, string> = useMemo(
    () => ({
      hostile: t("relationTypes.hostile"),
      allied: t("relationTypes.allied"),
      cold_war: t("relationTypes.coldWar"),
      dependent: t("relationTypes.dependent"),
      subordinate: t("relationTypes.subordinate"),
      trade_partner: t("relationTypes.tradePartner"),
      secret_cooperation: t("relationTypes.secretCooperation"),
      historical_enemy: t("relationTypes.historicalEnemy"),
    }),
    [t],
  );

  const categoryItems = useMemo(
    () => [
      { key: "core" as const, label: t("categories.core"), count: factions.length },
      { key: "volume" as const, label: t("categories.volume"), count: 0 },
      { key: "local" as const, label: t("categories.local"), count: 0 },
    ],
    [factions.length, t],
  );

  const loadData = useCallback(async () => {
    if (!novelId) return;
    try {
      setLoading(true);
      setError("");
      const [factionRes, relationRes, trashRes] = await Promise.all([
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${novelId}/level/core`),
        apiGet<{ data: FactionRelation[] }>(`/api/faction-relations/novel/${novelId}`),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${novelId}/trash?level_type=core`),
      ]);
      setFactions(mergeUniqueByKey([], factionRes.data.map((item, index) => createFactionDraft(item, index)), getFactionRenderKey));
      setRelations(mergeUniqueByKey([], relationRes.data, getRelationRenderKey));
      setTrashFactions(mergeUniqueByKey([], trashRes.data.map((item, index) => createFactionDraft(item, index)), getFactionRenderKey));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [novelId]);

  useEffect(() => {
    if (canUseSavedNovel) {
      loadData();
    }
  }, [canUseSavedNovel, loadData]);

  const handleGenerate = async () => {
    if (!novelId || !canGenerateCoreFactions) return;
    try {
      setGenerating(true);
      setError("");
      const result = await apiPost<CoreFactionsPayload>("/api/llm/generate-core-factions", {
        novel_id: novelId,
      });
      setPreview(normalizeGeneratedPayload(result));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  };

  const handleSavePreview = async () => {
    if (!novelId || !preview) return;
    try {
      setSaving(true);
      setError("");
      const saved = await apiPost<BulkCreateCoreFactionsResponse>(
        `/api/factions/novel/${novelId}/bulk-core-with-relations`,
        preview,
      );
      setFactions((prev) => mergeUniqueByKey(prev, saved.factions.map((item, index) => createFactionDraft(item, index)), getFactionRenderKey));
      setRelations((prev) => mergeUniqueByKey(prev, saved.faction_relations, getRelationRenderKey));
      setPreview(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleOpenCreate = () => {
    setActiveCategory("core");
    setEditor({
      mode: "create",
      draft: createFactionDraft({ sort_order: (factions.length + 1) * 10 }, factions.length),
    });
  };

  const handleOpenEdit = (faction: CoreFaction) => {
    setActiveCategory("core");
    setEditor({ mode: "edit", draft: createFactionDraft(faction) });
  };

  const handleSaveEditor = async () => {
    if (!novelId || !editor) return;
    const request = buildFactionRequest(editor.draft);
    if (!request.name) {
      setError(t("validation.nameRequired"));
      return;
    }

    try {
      setSaving(true);
      setError("");
      if (editor.mode === "create") {
        await apiPost(`/api/factions/novel/${novelId}/create`, request);
      } else if (editor.draft.faction_id) {
        await apiPut(`/api/factions/novel/${novelId}/${editor.draft.faction_id}`, request);
      }
      setEditor(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!novelId || !deleteIntent?.faction.faction_id) return;
    const factionId = deleteIntent.faction.faction_id;
    const requestKey = `${deleteIntent.mode}:${factionId}`;
    try {
      setActionId(requestKey);
      setError("");
      if (deleteIntent.mode === "soft") {
        await apiDelete(`/api/factions/novel/${novelId}/${factionId}`);
      } else {
        await apiDelete(`/api/factions/novel/${novelId}/${factionId}/hard`);
      }
      setDeleteIntent(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const handleRestore = async (faction: CoreFaction) => {
    if (!novelId || !faction.faction_id) return;
    const requestKey = `restore:${faction.faction_id}`;
    try {
      setActionId(requestKey);
      setError("");
      await apiPost(`/api/factions/novel/${novelId}/${faction.faction_id}/restore`, {});
      await loadData();
      setActiveCategory("core");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const updatePreviewFaction = (index: number, patch: Partial<CoreFaction>) => {
    setPreview((prev) => {
      if (!prev) return prev;
      const nextFactions = [...prev.core_factions];
      const currentName = nextFactions[index].name;
      nextFactions[index] = { ...nextFactions[index], ...patch };

      // 关系预览使用阵营名称引用，阵营改名时同步维护引用避免保存失败。
      const nextRelations = prev.faction_relations.map((relation) => ({
        ...relation,
        source_faction_name:
          relation.source_faction_name === currentName && patch.name
            ? patch.name
            : relation.source_faction_name,
        target_faction_name:
          relation.target_faction_name === currentName && patch.name
            ? patch.name
            : relation.target_faction_name,
      }));

      return { core_factions: nextFactions, faction_relations: nextRelations };
    });
  };

  const updatePreviewRelation = (index: number, patch: Partial<GeneratedFactionRelation>) => {
    setPreview((prev) => {
      if (!prev) return prev;
      const nextRelations = [...prev.faction_relations];
      nextRelations[index] = { ...nextRelations[index], ...patch };
      return { ...prev, faction_relations: nextRelations };
    });
  };

  if (!canUseSavedNovel) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="max-w-sm text-center">
          <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
          <p className="mt-2 text-sm text-muted">{t("createModeUnavailable")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col overflow-hidden md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-border bg-surface md:w-52 md:border-b-0 md:border-r">
        <div className="border-b border-border px-4 py-4">
          <h2 className="text-base font-semibold text-foreground">{t("title")}</h2>
          <p className="mt-1 text-xs leading-5 text-muted">{t("subtitle")}</p>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 py-3 md:block md:flex-1 md:space-y-1 md:overflow-y-auto">
          {categoryItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setActiveCategory(item.key)}
              className={`flex min-w-fit items-center justify-between gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors md:w-full ${
                activeCategory === item.key
                  ? "bg-accent/10 text-accent"
                  : "text-muted hover:bg-surface-secondary hover:text-foreground"
              }`}
            >
              <span>{item.label}</span>
              <span className="rounded bg-background px-1.5 py-0.5 text-xs text-muted">{item.count}</span>
            </button>
          ))}
        </nav>
        <div className="border-t border-border px-3 py-3">
          <button
            onClick={() => setActiveCategory("trash")}
            className={`flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              activeCategory === "trash"
                ? "bg-accent/10 text-accent"
                : "text-muted hover:bg-surface-secondary hover:text-foreground"
            }`}
          >
            <span>{t("categories.trash")}</span>
            <span className="rounded bg-background px-1.5 py-0.5 text-xs text-muted">{trashFactions.length}</span>
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-lg font-bold text-foreground">{t(`categoryTitles.${activeCategory}`)}</h3>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
                <span className="rounded-md border border-border bg-surface px-2 py-1">
                  {t("coreCount", { count: factions.length })}
                </span>
                <span className="rounded-md border border-border bg-surface px-2 py-1">
                  {t("relationCount", { count: relations.length })}
                </span>
                <span className="rounded-md border border-border bg-surface px-2 py-1">
                  {t("trashCount", { count: trashFactions.length })}
                </span>
              </div>
            </div>

            {activeCategory === "core" && (
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onPress={loadData} isDisabled={loading || saving || generating}>
                  {loading ? t("loading") : t("refresh")}
                </Button>
                <Button variant="outline" size="sm" onPress={handleOpenCreate} isDisabled={saving || generating}>
                  {t("manualCreate")}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  className="bg-accent text-white hover:bg-accent-hover"
                  onPress={handleGenerate}
                  isDisabled={generating || saving || !canGenerateCoreFactions}
                >
                  {generating ? t("generating") : t("generate")}
                </Button>
              </div>
            )}
          </div>
          {error && (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </div>
          )}
          {activeCategory === "core" && !canGenerateCoreFactions && !preview && (
            <InfoBlock tone="muted" text={t("generateLocked")} />
          )}
          {activeCategory === "core" && shouldWarnTooManyCoreFactions && (
            <InfoBlock tone="warning" text={t("tooManyWarning")} />
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {activeCategory === "core" && (
            <div className="grid gap-5">
              <div className="min-w-0">
                {preview && (
                  <section className="mb-6 border-b border-dashed border-border pb-6">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h4 className="text-base font-semibold text-foreground">{t("previewTitle")}</h4>
                        <p className="text-xs text-muted">
                          {t("previewMeta", {
                            factions: preview.core_factions.length,
                            relations: preview.faction_relations.length,
                          })}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onPress={() => setPreview(null)} isDisabled={saving}>
                          {t("discardPreview")}
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          className="bg-accent text-white hover:bg-accent-hover"
                          onPress={handleSavePreview}
                          isDisabled={saving}
                        >
                          {saving ? t("saving") : t("savePreview")}
                        </Button>
                      </div>
                    </div>

                    <FactionPreviewEditor
                      preview={preview}
                      relationTypeLabels={relationTypeLabels}
                      onFactionChange={updatePreviewFaction}
                      onRelationChange={updatePreviewRelation}
                      t={t}
                    />
                  </section>
                )}

                <section>
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="text-base font-semibold text-foreground">{t("savedFactions")}</h4>
                  </div>
                  {factions.length === 0 ? (
                    <EmptyBlock text={t("emptyFactions")} />
                  ) : (
                    <div className="grid gap-3 lg:grid-cols-2">
                      {factions.map((faction) => (
                        <FactionCard
                          key={getFactionRenderKey(faction)}
                          faction={faction}
                          onEdit={() => handleOpenEdit(faction)}
                          onDelete={() => setDeleteIntent({ mode: "soft", faction })}
                          t={t}
                        />
                      ))}
                    </div>
                  )}
                </section>

                <section className="mt-6">
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="text-base font-semibold text-foreground">{t("savedRelations")}</h4>
                  </div>
                  {relations.length === 0 ? (
                    <EmptyBlock text={t("emptyRelations")} />
                  ) : (
                    <div className="grid gap-3 xl:grid-cols-2">
                      {relations.map((relation) => (
                        <RelationRow
                          key={getRelationRenderKey(relation)}
                          relation={relation}
                          relationTypeLabels={relationTypeLabels}
                        />
                      ))}
                    </div>
                  )}
                </section>
              </div>
            </div>
          )}

          {(activeCategory === "volume" || activeCategory === "local") && (
            <ReservedCategory title={t(`categoryTitles.${activeCategory}`)} text={t("reservedCategory")} />
          )}

          {activeCategory === "trash" && (
            <TrashPanel
              factions={trashFactions}
              actionId={actionId}
              onRestore={handleRestore}
              onHardDelete={(faction) => setDeleteIntent({ mode: "hard", faction })}
              t={t}
            />
          )}
        </div>
      </div>

      {editor && (
        <EditorModal
          editor={editor}
          saving={saving}
          onChange={(draft) => setEditor((prev) => (prev ? { ...prev, draft } : prev))}
          onCancel={() => setEditor(null)}
          onSave={handleSaveEditor}
          t={t}
        />
      )}

      {deleteIntent && (
          <ConfirmLayer
          title={deleteIntent.mode === "soft" ? t("deleteConfirmTitle") : t("hardDeleteConfirmTitle")}
          message={
            deleteIntent.mode === "soft"
              ? t("deleteConfirmMessage", { name: deleteIntent.faction.name })
              : t("hardDeleteConfirmMessage", { name: deleteIntent.faction.name })
          }
          confirmText={deleteIntent.mode === "soft" ? t("delete") : t("hardDelete")}
          danger={deleteIntent.mode === "hard"}
          isLoading={actionId === `${deleteIntent.mode}:${deleteIntent.faction.faction_id}`}
          onCancel={() => setDeleteIntent(null)}
          onConfirm={handleConfirmDelete}
          cancelText={t("cancel")}
          loadingText={t("processing")}
        />
      )}
    </div>
  );
}

interface FactionPreviewEditorProps {
  preview: CoreFactionsPayload;
  relationTypeLabels: Record<FactionRelationType, string>;
  onFactionChange: (index: number, patch: Partial<CoreFaction>) => void;
  onRelationChange: (index: number, patch: Partial<GeneratedFactionRelation>) => void;
  t: ReturnType<typeof useTranslations>;
}

function FactionPreviewEditor({
  preview,
  relationTypeLabels,
  onFactionChange,
  onRelationChange,
  t,
}: FactionPreviewEditorProps) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
      <div className="grid gap-3">
        {preview.core_factions.map((faction, index) => (
          <div key={`${faction.name}-${index}`} className="rounded-md border border-border bg-surface p-4">
            <FactionEditor value={faction} onChange={(patch) => onFactionChange(index, patch)} t={t} />
          </div>
        ))}
      </div>

      <div className="space-y-3">
        {preview.faction_relations.map((relation, index) => (
          <div key={`${relation.source_faction_name}-${relation.target_faction_name}-${index}`} className="rounded-md border border-border bg-surface p-4">
            <div className="grid gap-3">
              <SelectInput
                label={t("fields.sourceFaction")}
                value={relation.source_faction_name}
                options={preview.core_factions.map((faction) => faction.name)}
                onChange={(value) => onRelationChange(index, { source_faction_name: value })}
              />
              <SelectInput
                label={t("fields.targetFaction")}
                value={relation.target_faction_name}
                options={preview.core_factions.map((faction) => faction.name)}
                onChange={(value) => onRelationChange(index, { target_faction_name: value })}
              />
              <SelectInput
                label={t("fields.relationType")}
                value={relation.relation_type}
                options={RELATION_TYPES}
                optionLabel={(option) => relationTypeLabels[option as FactionRelationType]}
                onChange={(value) => onRelationChange(index, { relation_type: value as FactionRelationType })}
              />
              <TextInput label={t("fields.currentState")} value={relation.current_state} onChange={(value) => onRelationChange(index, { current_state: value })} />
              <TextArea label={t("fields.coreConflict")} value={relation.core_conflict} onChange={(value) => onRelationChange(index, { core_conflict: value })} />
              <TextArea label={t("fields.hiddenTension")} value={relation.hidden_tension ?? ""} onChange={(value) => onRelationChange(index, { hidden_tension: value })} />
              <TextArea label={t("fields.possibleChange")} value={relation.possible_change} onChange={(value) => onRelationChange(index, { possible_change: value })} />
              <label className="grid gap-1 text-sm">
                <span className="text-xs font-medium text-muted">{t("fields.intensity")}: {relation.intensity}</span>
                <input
                  type="range"
                  min={1}
                  max={5}
                  value={relation.intensity}
                  onChange={(event) => onRelationChange(index, { intensity: Number(event.target.value) })}
                  className="accent-[var(--color-accent)]"
                />
              </label>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FactionEditor({
  value,
  onChange,
  t,
}: {
  value: CoreFaction;
  onChange: (patch: Partial<CoreFaction>) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <TextInput label={t("fields.name")} value={value.name} required onChange={(name) => onChange({ name })} />
      <TextInput label={t("fields.factionType")} value={value.faction_type} onChange={(faction_type) => onChange({ faction_type })} />
      <TextArea label={t("fields.positioning")} value={value.positioning} onChange={(positioning) => onChange({ positioning })} />
      <TextArea label={t("fields.publicStance")} value={value.public_stance} onChange={(public_stance) => onChange({ public_stance })} />
      <TextArea label={t("fields.coreGoal")} value={value.core_goal} onChange={(core_goal) => onChange({ core_goal })} />
      <TextArea label={t("fields.hiddenGoal")} value={value.hidden_goal ?? ""} onChange={(hidden_goal) => onChange({ hidden_goal })} />
      <TextArea label={t("fields.resources")} value={joinListText(value.resources_and_advantages)} onChange={(text) => onChange({ resources_and_advantages: splitListText(text) })} />
      <TextArea label={t("fields.values")} value={joinListText(value.core_values)} onChange={(text) => onChange({ core_values: splitListText(text) })} />
      <TextArea label={t("fields.conflict")} value={value.conflict_with_mainline} onChange={(conflict_with_mainline) => onChange({ conflict_with_mainline })} />
      <TextArea label={t("fields.expandability")} value={value.expandability} onChange={(expandability) => onChange({ expandability })} />
      <TextInput label={t("fields.organizationStyle")} value={value.organization_style} onChange={(organization_style) => onChange({ organization_style })} />
      <TextInput label={t("fields.influenceScope")} value={value.influence_scope} onChange={(influence_scope) => onChange({ influence_scope })} />
      <TextArea label={t("fields.tags")} value={joinListText(value.tags)} onChange={(text) => onChange({ tags: splitListText(text) })} />
      <label className="flex items-center gap-2 self-end text-sm text-foreground">
        <input
          type="checkbox"
          checked={value.is_public}
          onChange={(event) => onChange({ is_public: event.target.checked })}
          className="h-4 w-4 accent-[var(--color-accent)]"
        />
        {t("fields.isPublic")}
      </label>
    </div>
  );
}

function EditorModal({
  editor,
  saving,
  onChange,
  onCancel,
  onSave,
  t,
}: {
  editor: NonNullable<EditorState>;
  saving: boolean;
  onChange: (draft: CoreFaction) => void;
  onCancel: () => void;
  onSave: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/20 px-4 py-6">
      <div className="flex max-h-full w-full max-w-4xl flex-col rounded-md border border-border bg-surface shadow-lg">
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <h4 className="text-sm font-semibold text-foreground">
            {editor.mode === "create" ? t("editor.createTitle") : t("editor.editTitle")}
          </h4>
          <button
            type="button"
            onClick={onCancel}
            className="grid h-8 w-8 place-items-center rounded-md text-muted transition-colors hover:bg-surface-secondary hover:text-foreground"
            aria-label={t("cancel")}
            title={t("cancel")}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto p-4">
          <FactionEditor
            value={editor.draft}
            onChange={(patch) => onChange({ ...editor.draft, ...patch })}
            t={t}
          />
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <Button variant="ghost" size="sm" onPress={onCancel} isDisabled={saving}>
            {t("cancel")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            className="bg-accent text-white hover:bg-accent-hover"
            onPress={onSave}
            isDisabled={saving}
          >
            {saving ? t("saving") : t("save")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function FactionCard({
  faction,
  onEdit,
  onDelete,
  t,
}: {
  faction: CoreFaction;
  onEdit: () => void;
  onDelete: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <article className="rounded-md border border-border bg-surface p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-foreground">{faction.name}</h4>
          <p className="mt-0.5 text-xs text-muted">{faction.faction_type || t("card.typeEmpty")}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <IconButton label={t("edit")} onClick={onEdit}>
            <path d="M12 20h9" />
            <path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z" />
          </IconButton>
          <IconButton label={t("delete")} onClick={onDelete}>
            <path d="M3 6h18" />
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          </IconButton>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        <span className="rounded-md bg-accent/10 px-2 py-1 text-xs font-medium text-accent">
          {faction.is_public ? t("publicStatus.public") : t("publicStatus.hidden")}
        </span>
        {(faction.tags ?? []).slice(0, 3).map((tag) => (
          <span key={tag} className="rounded-md border border-border px-2 py-1 text-xs text-muted">
            {tag}
          </span>
        ))}
      </div>
      <div className="space-y-2 text-xs leading-5 text-foreground">
        <p><span className="font-medium text-muted">{t("card.positioning")}</span> {faction.positioning || t("card.emptyValue")}</p>
        <p><span className="font-medium text-muted">{t("card.goal")}</span> {faction.core_goal || t("card.emptyValue")}</p>
        <p><span className="font-medium text-muted">{t("card.conflict")}</span> {faction.conflict_with_mainline || t("card.emptyValue")}</p>
      </div>
      {faction.resources_and_advantages?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {faction.resources_and_advantages.slice(0, 4).map((item) => (
            <span key={item} className="rounded-md border border-border px-2 py-0.5 text-xs text-muted">
              {item}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

function TrashPanel({
  factions,
  actionId,
  onRestore,
  onHardDelete,
  t,
}: {
  factions: CoreFaction[];
  actionId: string;
  onRestore: (faction: CoreFaction) => void;
  onHardDelete: (faction: CoreFaction) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  if (factions.length === 0) {
    return <EmptyBlock text={t("trashEmpty")} />;
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {factions.map((faction) => (
        <article key={getFactionRenderKey(faction)} className="rounded-md border border-border bg-surface p-4">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h4 className="truncate text-sm font-semibold text-foreground">{faction.name}</h4>
              <p className="mt-0.5 text-xs text-muted">{faction.faction_type || t("card.typeEmpty")}</p>
            </div>
            <span className="rounded-md border border-border px-2 py-1 text-xs text-muted">{t("deletedStatus")}</span>
          </div>
          <p className="text-xs leading-5 text-foreground">{faction.positioning || t("card.emptyValue")}</p>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onPress={() => onRestore(faction)}
              isDisabled={actionId === `restore:${faction.faction_id}`}
            >
              {actionId === `restore:${faction.faction_id}` ? t("restoring") : t("restore")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-red-200 text-red-600 hover:border-red-300 hover:bg-red-50 dark:border-red-900/70 dark:hover:bg-red-950/30"
              onPress={() => onHardDelete(faction)}
            >
              {t("hardDelete")}
            </Button>
          </div>
        </article>
      ))}
    </div>
  );
}

function RelationRow({
  relation,
  relationTypeLabels,
}: {
  relation: FactionRelation;
  relationTypeLabels: Record<FactionRelationType, string>;
}) {
  return (
    <article className="rounded-md border border-border bg-surface p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 text-sm font-semibold text-foreground">
          <span>{relation.source_faction_name ?? relation.source_faction_id}</span>
          <span className="mx-2 text-muted">→</span>
          <span>{relation.target_faction_name ?? relation.target_faction_id}</span>
        </div>
        <span className="rounded-md bg-surface-secondary px-2 py-1 text-xs text-muted">
          {relationTypeLabels[relation.relation_type]}
        </span>
      </div>
      <p className="text-xs leading-5 text-foreground">{relation.core_conflict}</p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-secondary">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${Math.max(1, Math.min(5, relation.intensity)) * 20}%` }}
        />
      </div>
    </article>
  );
}

function ConfirmLayer({
  title,
  message,
  confirmText,
  danger,
  isLoading,
  cancelText,
  loadingText,
  onCancel,
  onConfirm,
}: {
  title: string;
  message: string;
  confirmText: string;
  danger?: boolean;
  isLoading: boolean;
  cancelText: string;
  loadingText: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/20 px-4">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-4 shadow-lg">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        <p className="mt-2 text-sm leading-6 text-muted">{message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onPress={onCancel} isDisabled={isLoading}>
            {cancelText}
          </Button>
          <Button
            variant="primary"
            size="sm"
            className={danger ? "bg-red-600 text-white hover:bg-red-700" : "bg-accent text-white hover:bg-accent-hover"}
            onPress={onConfirm}
            isDisabled={isLoading}
          >
            {isLoading ? loadingText : confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ReservedCategory({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="max-w-sm text-center">
        <h4 className="text-base font-semibold text-foreground">{title}</h4>
        <p className="mt-2 text-sm leading-6 text-muted">{text}</p>
      </div>
    </div>
  );
}

function InfoBlock({ text, tone }: { text: string; tone: "muted" | "warning" }) {
  const className =
    tone === "warning"
      ? "mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200"
      : "mt-3 rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted";
  return <div className={className}>{text}</div>;
}

function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-dashed border-border bg-surface/70 px-4 py-8 text-center text-sm text-muted">
      {text}
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className="grid h-8 w-8 place-items-center rounded-md text-muted transition-colors hover:bg-surface-secondary hover:text-foreground"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {children}
      </svg>
    </button>
  );
}

function TextInput({
  label,
  value,
  required,
  onChange,
}: {
  label: string;
  value: string;
  required?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-xs font-medium text-muted">{label}{required ? " *" : ""}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-9 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-xs font-medium text-muted">{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={3}
        className="min-h-20 resize-y rounded-md border border-border bg-background px-3 py-2 text-sm leading-5 text-foreground outline-none focus:border-accent"
      />
    </label>
  );
}

function SelectInput({
  label,
  value,
  options,
  optionLabel,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  optionLabel?: (value: string) => string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-xs font-medium text-muted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-9 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {optionLabel ? optionLabel(option) : option}
          </option>
        ))}
      </select>
    </label>
  );
}
