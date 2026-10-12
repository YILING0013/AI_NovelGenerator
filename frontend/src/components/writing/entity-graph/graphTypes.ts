import type {
  CharacterFactionMembershipType,
  CharacterImportanceLevel,
  CharacterRelationType,
  CharacterRoleType,
} from "@/types/character";
import type { FactionRelationType } from "@/types/novel";

export type RelationshipGraphNodeKind = "character" | "faction";
export type RelationshipGraphEdgeKind =
  | "character_relation"
  | "faction_relation"
  | "membership"
  | "faction_hierarchy";
export type RelationshipGraphFactionLevel = "core" | "volume" | "local" | "unknown";

interface RelationshipGraphNodeBaseV1 {
  id: string;
  label: string;
  isActive: boolean;
  version: number;
  updatedAt: string | null;
  searchText: string;
}

export interface RelationshipGraphCharacterNodeV1 extends RelationshipGraphNodeBaseV1 {
  kind: "character";
  characterId: string;
  roleType: CharacterRoleType;
  importanceLevel: CharacterImportanceLevel;
  isCoreCharacter: boolean;
  identity: string;
  storyFunction: string;
  tags: string[];
}

export interface RelationshipGraphFactionNodeV1 extends RelationshipGraphNodeBaseV1 {
  kind: "faction";
  factionId: string;
  level: RelationshipGraphFactionLevel;
  factionType: string;
  parentFactionId: string | null;
  positioning: string;
  publicStance: string;
  tags: string[];
}

export type RelationshipGraphNodeV1 =
  | RelationshipGraphCharacterNodeV1
  | RelationshipGraphFactionNodeV1;

interface RelationshipGraphEdgeBaseV1 {
  id: string;
  source: string;
  target: string;
  label: string;
  isActive: boolean;
  directed: boolean;
  intensity: number | null;
  version: number;
  updatedAt: string | null;
}

export interface RelationshipGraphCharacterRelationEdgeV1
  extends RelationshipGraphEdgeBaseV1 {
  kind: "character_relation";
  relationId: string;
  relationType: CharacterRelationType;
  currentState: string;
  coreConflict: string;
}

export interface RelationshipGraphFactionRelationEdgeV1
  extends RelationshipGraphEdgeBaseV1 {
  kind: "faction_relation";
  relationId: string;
  relationType: FactionRelationType;
  currentState: string;
  coreConflict: string;
}

export interface RelationshipGraphMembershipEdgeV1 extends RelationshipGraphEdgeBaseV1 {
  kind: "membership";
  bindingId: string;
  membershipType: CharacterFactionMembershipType;
  roleTitle: string | null;
  publicStatus: string | null;
  loyaltyLevel: number | null;
  notes: string | null;
}

export interface RelationshipGraphFactionHierarchyEdgeV1
  extends RelationshipGraphEdgeBaseV1 {
  kind: "faction_hierarchy";
  childFactionId: string;
  parentFactionId: string;
}

export type RelationshipGraphEdgeV1 =
  | RelationshipGraphCharacterRelationEdgeV1
  | RelationshipGraphFactionRelationEdgeV1
  | RelationshipGraphMembershipEdgeV1
  | RelationshipGraphFactionHierarchyEdgeV1;

export type RelationshipGraphDiagnosticCode =
  | "missing_business_id"
  | "duplicate_node_id"
  | "duplicate_edge_id"
  | "missing_endpoint"
  | "self_reference"
  | "unknown_faction_level";

export interface RelationshipGraphDiagnosticV1 {
  code: RelationshipGraphDiagnosticCode;
  severity: "warning";
  entityKind: RelationshipGraphNodeKind | RelationshipGraphEdgeKind;
  entityId: string | null;
  message: string;
  details?: Record<string, string>;
}

export interface RelationshipGraphSnapshotV1 {
  novelId: string;
  nodes: RelationshipGraphNodeV1[];
  edges: RelationshipGraphEdgeV1[];
  diagnostics: RelationshipGraphDiagnosticV1[];
  loadedAt: string;
  contentVersion: string;
}

export interface RelationshipGraphFilters {
  query: string;
  showInactive: boolean;
  nodeKinds: Record<RelationshipGraphNodeKind, boolean>;
  factionLevels: Record<Exclude<RelationshipGraphFactionLevel, "unknown">, boolean>;
  characterImportance: Record<CharacterImportanceLevel, boolean>;
  edgeKinds: Record<RelationshipGraphEdgeKind, boolean>;
}

export interface RelationshipGraphProjection {
  nodes: RelationshipGraphNodeV1[];
  edges: RelationshipGraphEdgeV1[];
  matchedNodeIds: Set<string>;
  hiddenNodeCount: number;
  hiddenEdgeCount: number;
}

export interface RelationshipGraphTopologyDiff {
  topologyChanged: boolean;
  contentChanged: boolean;
  addedNodeIds: string[];
  removedNodeIds: string[];
  retainedNodeIds: string[];
}

