import type { CandidateBasisV1 } from "@/lib/aiCandidate";

export type HierarchyKind = "volume" | "arc" | "scene" | "chapter";
export type PlanningKind = Exclude<HierarchyKind, "volume">;

export interface PartPlanning {
  goal: string;
  start_state: string;
  end_state: string;
  key_beats: string[];
  continuity_notes: string;
  target_chapter_count: number | null;
  target_word_count: number | null;
  character_ids: string[];
  faction_ids: string[];
  location_ids: string[];
  item_ids: string[];
  rule_ids: string[];
}

export interface ChapterPlanning {
  goal: string;
  start_state: string;
  end_state: string;
  beats: string[];
  pov_character_id: string | null;
  must_include: string[];
  must_avoid: string[];
  target_word_count: number | null;
}

/** 目录不携带正文；只有章节详情响应提供 content。 */
export interface HierarchyRecord {
  novel_id: string;
  volume_id: string;
  arc_id?: string;
  scene_id?: string;
  chapter_id?: string;
  title: string;
  summary: string;
  subtitle?: string;
  goal?: string;
  theme?: string;
  location_ids?: string[];
  planning: PartPlanning | ChapterPlanning | Record<string, unknown> | null;
  order_index: number;
  version: number;
  is_deleted: boolean;
  word_count: number;
  chapter_count?: number;
  chapter_number?: number | null;
  scenes_count?: number;
  arcs_count?: number;
  content?: string;
  plot?: string;
  plot_source_fingerprint?: string | null;
}

export interface HierarchyNode {
  kind: HierarchyKind;
  id: string;
  record: HierarchyRecord;
}

export interface HierarchyLocation {
  volume_id?: string | null;
  arc_id?: string | null;
  scene_id?: string | null;
  chapter_id?: string | null;
  revision_version?: string | null;
}

export interface ChapterRevision {
  revision_id: string;
  chapter_id: string;
  novel_id: string;
  volume_id: string;
  arc_id: string;
  scene_id: string;
  version: number;
  parent_version: number | null;
  title: string;
  source: "baseline" | "create" | "edit" | "writing" | "assistant" | "restore";
  content_hash: string;
  saved_at: string;
  restored_from_version?: number | null;
  summary: string;
  planning: ChapterPlanning;
  content: string;
}

export interface ChapterRevisionComparison {
  revision: ChapterRevision;
  current: HierarchyRecord;
  changed_fields: ("title" | "summary" | "planning" | "content")[];
  restore_normalizes_text: boolean;
}

export interface PlanningDraft {
  title: string;
  summary: string;
  planning: PartPlanning | ChapterPlanning;
}

export interface EntityChoice { id: string; name: string }
export type EntityChoices = Record<"character_ids" | "faction_ids" | "location_ids" | "item_ids" | "rule_ids", EntityChoice[]>;

export interface WritingCandidateBasisV1 extends CandidateBasisV1 {
  generation_input: Record<string, unknown>;
  context_basis: {
    version: 1;
    reads: { kind: "parent_chain" | "children" | "neighbors" | "previous_written" | "selected_entities" | "volume_states" | "literal_search" | "edit_target"; scope: Record<string, unknown>; fingerprint: string }[];
  };
}

export interface HierarchyPreview {
  candidate: { arcs?: PlanningDraft[]; scenes?: PlanningDraft[]; chapters?: PlanningDraft[]; content?: string };
  basis: WritingCandidateBasisV1;
  coverage_review?: {
    schema_version?: 1;
    summary: string;
    issues: {
      candidate_index: number;
      message: string;
      candidate_field?: string;
      candidate_quote?: string;
      source?: { resource_type: string; id: string; field: string; quote: string } | null;
      verification?: {
        candidate: "matched" | "unverified";
        source: "matched" | "unverified" | "not_provided";
        status: "matched" | "unverified";
        source_truncated?: boolean | null;
        semantic_check?: "not_performed";
      };
    }[];
  } | null;
}

export interface PlanningReadiness {
  novel_id: string;
  target_type: HierarchyKind;
  target_id: string;
  can_create_child: boolean;
  create_missing_fields: { field: string; message: string }[];
  can_refine: boolean;
  can_write: boolean;
  missing_fields: { field: string; message: string }[];
  blockers: { code: string; message: string }[];
  parent_chain: { resource_type: string; id: string; title: string }[];
  expected_version: number;
  can_generate_plot?: boolean;
  plot_status?: "missing" | "stale" | "ready";
  preparation?: { factions: boolean; characters: boolean; locations: boolean };
}

/** 功能：构造人工规划草稿。Args: kind 当前层级。Returns: 可直接编辑的空计划。 */
export function emptyPlanningDraft(kind: PlanningKind): PlanningDraft {
  const common = { goal: "", start_state: "", end_state: "", target_word_count: null };
  return {
    title: "", summary: "",
    planning: kind === "chapter"
      ? { ...common, beats: [], pov_character_id: null, must_include: [], must_avoid: [] }
      : { ...common, key_beats: [], continuity_notes: "", target_chapter_count: null, character_ids: [], faction_ids: [], location_ids: [], item_ids: [], rule_ids: [] },
  };
}

/** 功能：将目录或详情加入同一层级树。Args: kind 层级；record API数据。Returns: 稳定节点。 */
export function hierarchyNode(kind: HierarchyKind, record: HierarchyRecord): HierarchyNode {
  return { kind, id: record[`${kind}_id`]!, record };
}

/** 功能：生成节点所属父链。Args: node 当前节点。Returns: URL使用的稳定ID。 */
export function hierarchyLocation(node: HierarchyNode): HierarchyLocation {
  const r = node.record;
  return { volume_id: r.volume_id, arc_id: r.arc_id, scene_id: r.scene_id, chapter_id: r.chapter_id };
}

export const CHILD_KIND: Record<Exclude<HierarchyKind, "chapter">, PlanningKind> = { volume: "arc", arc: "scene", scene: "chapter" };

/** 功能：定位父节点的子级接口。Args: node 父节点。Returns: 目录、创建和确认共用路径。 */
export function hierarchyChildrenUrl(node: HierarchyNode): string {
  const child = CHILD_KIND[node.kind as Exclude<HierarchyKind, "chapter">];
  return `/api/${child}s/${node.kind}/${node.id}`;
}
