export type ForeshadowingStatus = "planned" | "planted" | "resolved" | "abandoned";
export type ForeshadowingPosition = { kind: "volume" | "arc" | "scene"; id: string };
export type ForeshadowingEvidenceInput = { chapter_id: string; version: number; start: number; quote: string };
export type ForeshadowingEvidence = ForeshadowingEvidenceInput & { revision_id: string; content_hash: string };
export interface ForeshadowingPlan {
  title: string;
  content: string;
  target_effect: string;
  planting_position: ForeshadowingPosition | null;
  resolution_position: ForeshadowingPosition | null;
}
export interface Foreshadowing extends ForeshadowingPlan {
  foreshadowing_id: string;
  novel_id: string;
  status: ForeshadowingStatus;
  planted_evidence: ForeshadowingEvidence | null;
  resolved_evidence: ForeshadowingEvidence | null;
  planted_needs_review: boolean;
  resolved_needs_review: boolean;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}
export const FORESHADOWING_TRANSITIONS: Record<ForeshadowingStatus, ForeshadowingStatus[]> = {
  planned: ["planned", "planted", "abandoned"],
  planted: ["planted", "planned", "resolved", "abandoned"],
  resolved: ["resolved", "planted", "abandoned"],
  abandoned: ["abandoned", "planned", "planted"],
};
