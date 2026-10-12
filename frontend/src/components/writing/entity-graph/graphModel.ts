import type {
  CharacterFactionBindingResponseV1,
  CharacterRelationResponseV1,
  CharacterResponseV1,
} from "@/types/character";
import type { CoreFaction, FactionRelation } from "@/types/novel";
import type {
  RelationshipGraphDiagnosticV1,
  RelationshipGraphEdgeV1,
  RelationshipGraphFactionLevel,
  RelationshipGraphFilters,
  RelationshipGraphNodeV1,
  RelationshipGraphProjection,
  RelationshipGraphSnapshotV1,
  RelationshipGraphTopologyDiff,
} from "./graphTypes";

export interface RelationshipGraphSourceDataV1 {
  characters: CharacterResponseV1[];
  factions: CoreFaction[];
  characterRelations: CharacterRelationResponseV1[];
  factionRelations: FactionRelation[];
  bindings: CharacterFactionBindingResponseV1[];
}

const SYMMETRIC_CHARACTER_RELATIONS = new Set([
  "friend",
  "romantic",
  "ally",
  "rival",
  "enemy",
]);
const SYMMETRIC_FACTION_RELATIONS = new Set([
  "hostile",
  "allied",
  "cold_war",
  "trade_partner",
  "secret_cooperation",
  "historical_enemy",
]);

/**
 * 功能：创建关系图谱的默认筛选状态，默认展示活动实体和全部正式关系层。
 * Args:
 *   无。
 * Returns:
 *   一份可由页面局部修改的筛选状态。
 */
export function createDefaultRelationshipGraphFilters(): RelationshipGraphFilters {
  return {
    query: "",
    showInactive: false,
    nodeKinds: { character: true, faction: true },
    factionLevels: { core: true, volume: true, local: true },
    characterImportance: {
      core: true,
      major: true,
      supporting: true,
      background: true,
    },
    edgeKinds: {
      character_relation: true,
      faction_relation: true,
      membership: true,
      faction_hierarchy: true,
    },
  };
}

function normalizeFactionLevel(level: string | undefined): RelationshipGraphFactionLevel {
  if (level === "core" || level === "volume" || level === "local") return level;
  return "unknown";
}

function normalizeSearchText(parts: Array<string | string[] | null | undefined>): string {
  return parts
    .flatMap((part) => (Array.isArray(part) ? part : [part]))
    .filter((part): part is string => Boolean(part))
    .join(" ")
    .toLocaleLowerCase();
}

function hashSnapshotContent(nodes: RelationshipGraphNodeV1[], edges: RelationshipGraphEdgeV1[]): string {
  const value = JSON.stringify({
    nodes: [...nodes].sort((a, b) => a.id.localeCompare(b.id)),
    edges: [...edges].sort((a, b) => a.id.localeCompare(b.id)),
  });
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function createDiagnostic(
  diagnostic: Omit<RelationshipGraphDiagnosticV1, "severity">,
): RelationshipGraphDiagnosticV1 {
  return { ...diagnostic, severity: "warning" };
}

/**
 * 功能：把角色、势力和三类关系整理成一份不会被改写的图数据。
 * Args:
 *   novelId: 当前小说 ObjectId。
 *   source: 六组请求合并后的正式领域数据；active/inactive 绑定已合并进 bindings。
 *   loadedAt: 本轮六组请求全部成功的时间，默认取当前时间。
 * Returns:
 *   使用稳定业务 ID 的节点、四类边、诊断与内容版本。
 */
export function createRelationshipGraphSnapshot(
  novelId: string,
  source: RelationshipGraphSourceDataV1,
  loadedAt = new Date().toISOString(),
): RelationshipGraphSnapshotV1 {
  const diagnostics: RelationshipGraphDiagnosticV1[] = [];
  const nodeById = new Map<string, RelationshipGraphNodeV1>();
  const edges: RelationshipGraphEdgeV1[] = [];
  const edgeIds = new Set<string>();

  const addNode = (
    node: RelationshipGraphNodeV1 | null,
    entityKind: "character" | "faction",
    rawId: string | undefined,
  ) => {
    if (!node) {
      diagnostics.push(
        createDiagnostic({
          code: "missing_business_id",
          entityKind,
          entityId: rawId ?? null,
          message: "实体缺少稳定业务 ID，已跳过。",
        }),
      );
      return;
    }
    if (nodeById.has(node.id)) {
      diagnostics.push(
        createDiagnostic({
          code: "duplicate_node_id",
          entityKind,
          entityId: node.id,
          message: "发现重复节点业务 ID，保留首条记录。",
        }),
      );
      return;
    }
    nodeById.set(node.id, node);
  };

  for (const character of source.characters) {
    if (character.is_deleted) continue;
    const characterId = character.character_id?.trim();
    addNode(
      characterId
        ? {
            id: `character:${characterId}`,
            kind: "character",
            characterId,
            label: character.name,
            isActive: character.status === "active",
            roleType: character.role_type,
            importanceLevel: character.importance_level,
            isCoreCharacter: character.is_core_character,
            identity: character.identity,
            storyFunction: character.story_function,
            tags: [...character.tags],
            version: character.version,
            updatedAt: character.updated_at,
            searchText: normalizeSearchText([
              character.name,
              character.aliases,
              character.identity,
              character.story_function,
              character.tags,
            ]),
          }
        : null,
      "character",
      character.character_id,
    );
  }

  for (const faction of source.factions) {
    if (faction.is_deleted) continue;
    const factionId = faction.faction_id?.trim();
    const level = normalizeFactionLevel(faction.level_type);
    if (factionId && level === "unknown") {
      diagnostics.push(
        createDiagnostic({
          code: "unknown_faction_level",
          entityKind: "faction",
          entityId: factionId,
          message: "势力层级无法识别，节点仍保留以便未来扩展。",
          details: { level: faction.level_type ?? "" },
        }),
      );
    }
    const factionWithTimestamps = faction as CoreFaction & { updated_at?: string };
    addNode(
      factionId
        ? {
            id: `faction:${factionId}`,
            kind: "faction",
            factionId,
            label: faction.name,
            isActive: (faction.active_status ?? "active") === "active",
            level,
            factionType: faction.faction_type,
            parentFactionId: faction.parent_faction_id ?? null,
            positioning: faction.positioning,
            publicStance: faction.public_stance,
            tags: [...faction.tags],
            version: faction.version,
            updatedAt: factionWithTimestamps.updated_at ?? null,
            searchText: normalizeSearchText([
              faction.name,
              faction.alias,
              faction.faction_type,
              faction.positioning,
              faction.public_stance,
              faction.tags,
            ]),
          }
        : null,
      "faction",
      faction.faction_id,
    );
  }

  const addEdge = (edge: RelationshipGraphEdgeV1 | null, kind: RelationshipGraphEdgeV1["kind"], rawId?: string) => {
    if (!edge) {
      diagnostics.push(
        createDiagnostic({
          code: "missing_business_id",
          entityKind: kind,
          entityId: rawId ?? null,
          message: "关系缺少稳定业务 ID，已跳过。",
        }),
      );
      return;
    }
    if (edge.source === edge.target) {
      diagnostics.push(
        createDiagnostic({
          code: "self_reference",
          entityKind: kind,
          entityId: edge.id,
          message: "自引用关系不会进入图谱。",
        }),
      );
      return;
    }
    const missing: string[] = [];
    if (!nodeById.has(edge.source)) missing.push(edge.source);
    if (!nodeById.has(edge.target)) missing.push(edge.target);
    if (missing.length > 0) {
      diagnostics.push(
        createDiagnostic({
          code: "missing_endpoint",
          entityKind: kind,
          entityId: edge.id,
          message: "关系端点不存在，已跳过且未创建虚构节点。",
          details: { missing: missing.join(",") },
        }),
      );
      return;
    }
    if (edgeIds.has(edge.id)) {
      diagnostics.push(
        createDiagnostic({
          code: "duplicate_edge_id",
          entityKind: kind,
          entityId: edge.id,
          message: "发现重复关系业务 ID，保留首条记录。",
        }),
      );
      return;
    }
    edgeIds.add(edge.id);
    edges.push(edge);
  };

  for (const relation of source.characterRelations) {
    if (relation.is_deleted) continue;
    const relationId = relation.relation_id?.trim();
    addEdge(
      relationId
        ? {
            id: `character_relation:${relationId}`,
            kind: "character_relation",
            relationId,
            source: `character:${relation.source_character_id}`,
            target: `character:${relation.target_character_id}`,
            relationType: relation.relation_type,
            label: relation.relation_type,
            isActive: relation.is_active,
            directed: !SYMMETRIC_CHARACTER_RELATIONS.has(relation.relation_type),
            intensity: relation.intensity,
            currentState: relation.current_state,
            coreConflict: relation.core_conflict,
            version: relation.version,
            updatedAt: relation.updated_at,
          }
        : null,
      "character_relation",
      relation.relation_id,
    );
  }

  for (const relation of source.factionRelations) {
    if (relation.is_deleted) continue;
    const relationId = relation.relation_id?.trim();
    addEdge(
      relationId
        ? {
            id: `faction_relation:${relationId}`,
            kind: "faction_relation",
            relationId,
            source: `faction:${relation.source_faction_id ?? ""}`,
            target: `faction:${relation.target_faction_id ?? ""}`,
            relationType: relation.relation_type,
            label: relation.relation_type,
            isActive: relation.is_active,
            directed: !SYMMETRIC_FACTION_RELATIONS.has(relation.relation_type),
            intensity: relation.intensity,
            currentState: relation.current_state,
            coreConflict: relation.core_conflict,
            version: relation.version ?? 1,
            updatedAt: relation.updated_at ?? null,
          }
        : null,
      "faction_relation",
      relation.relation_id,
    );
  }

  for (const binding of source.bindings) {
    if (binding.is_deleted) continue;
    const bindingId = binding.binding_id?.trim();
    addEdge(
      bindingId
        ? {
            id: `membership:${bindingId}`,
            kind: "membership",
            bindingId,
            source: `character:${binding.character_id}`,
            target: `faction:${binding.faction_id}`,
            membershipType: binding.membership_type,
            label: binding.membership_type,
            isActive: binding.is_active,
            directed: true,
            intensity: binding.loyalty_level,
            roleTitle: binding.role_title,
            publicStatus: binding.public_status,
            loyaltyLevel: binding.loyalty_level,
            notes: binding.notes,
            version: binding.version,
            updatedAt: binding.updated_at,
          }
        : null,
      "membership",
      binding.binding_id,
    );
  }

  for (const node of nodeById.values()) {
    if (node.kind !== "faction" || !node.parentFactionId) continue;
    const parentNodeId = `faction:${node.parentFactionId}`;
    const parent = nodeById.get(parentNodeId);
    addEdge(
      {
        id: `faction_hierarchy:${node.factionId}:${node.parentFactionId}`,
        kind: "faction_hierarchy",
        source: node.id,
        target: parentNodeId,
        childFactionId: node.factionId,
        parentFactionId: node.parentFactionId,
        label: "parent_faction",
        isActive: node.isActive && Boolean(parent?.isActive),
        directed: true,
        intensity: null,
        version: node.version,
        updatedAt: node.updatedAt,
      },
      "faction_hierarchy",
    );
  }

  const nodes = [...nodeById.values()];
  return {
    novelId,
    nodes,
    edges,
    diagnostics,
    loadedAt,
    contentVersion: hashSnapshotContent(nodes, edges),
  };
}

/**
 * 功能：按筛选条件生成可见图数据，同时保留搜索结果用于聚焦和淡化其他节点。
 * Args:
 *   snapshot: 最近一次完整图谱快照。
 *   filters: 节点类型、势力层级、角色重要性、边层和活动状态筛选。
 * Returns:
 *   可见节点与边、搜索匹配 ID，以及隐藏数量。
 */
export function filterRelationshipGraph(
  snapshot: RelationshipGraphSnapshotV1,
  filters: RelationshipGraphFilters,
): RelationshipGraphProjection {
  const visibleNodes = snapshot.nodes.filter((node) => {
    if (!filters.showInactive && !node.isActive) return false;
    if (!filters.nodeKinds[node.kind]) return false;
    if (node.kind === "character") return filters.characterImportance[node.importanceLevel];
    if (node.level === "unknown") return true;
    return filters.factionLevels[node.level];
  });
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = snapshot.edges.filter(
    (edge) =>
      filters.edgeKinds[edge.kind] &&
      (filters.showInactive || edge.isActive) &&
      visibleNodeIds.has(edge.source) &&
      visibleNodeIds.has(edge.target),
  );
  const query = filters.query.trim().toLocaleLowerCase();
  const matchedNodeIds = new Set(
    visibleNodes
      .filter((node) => !query || node.searchText.includes(query))
      .map((node) => node.id),
  );
  return {
    nodes: visibleNodes,
    edges: visibleEdges,
    matchedNodeIds,
    hiddenNodeCount: snapshot.nodes.length - visibleNodes.length,
    hiddenEdgeCount: snapshot.edges.length - visibleEdges.length,
  };
}

/**
 * 功能：比较两次完整快照的拓扑和内容版本，为仿真保位与按需重热提供边界。
 * Args:
 *   previous: 上一次成功快照，首次加载时为 null。
 *   next: 本次成功快照。
 * Returns:
 *   节点增删、保留集合以及拓扑/内容是否变化。
 */
export function compareRelationshipGraphSnapshots(
  previous: RelationshipGraphSnapshotV1 | null,
  next: RelationshipGraphSnapshotV1,
): RelationshipGraphTopologyDiff {
  if (!previous) {
    return {
      topologyChanged: true,
      contentChanged: true,
      addedNodeIds: next.nodes.map((node) => node.id),
      removedNodeIds: [],
      retainedNodeIds: [],
    };
  }
  const previousNodeIds = new Set(previous.nodes.map((node) => node.id));
  const nextNodeIds = new Set(next.nodes.map((node) => node.id));
  // 相同业务边 ID 的端点或类型若发生变化，也属于需要重热仿真的拓扑变化。
  const previousEdgeTopology = new Set(
    previous.edges.map((edge) => JSON.stringify([edge.id, edge.kind, edge.source, edge.target])),
  );
  const nextEdgeTopology = new Set(
    next.edges.map((edge) => JSON.stringify([edge.id, edge.kind, edge.source, edge.target])),
  );
  const addedNodeIds = [...nextNodeIds].filter((id) => !previousNodeIds.has(id));
  const removedNodeIds = [...previousNodeIds].filter((id) => !nextNodeIds.has(id));
  const retainedNodeIds = [...nextNodeIds].filter((id) => previousNodeIds.has(id));
  const edgeTopologyChanged =
    previousEdgeTopology.size !== nextEdgeTopology.size ||
    [...nextEdgeTopology].some((signature) => !previousEdgeTopology.has(signature));
  return {
    topologyChanged: addedNodeIds.length > 0 || removedNodeIds.length > 0 || edgeTopologyChanged,
    contentChanged: previous.contentVersion !== next.contentVersion,
    addedNodeIds,
    removedNodeIds,
    retainedNodeIds,
  };
}
