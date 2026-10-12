/** 小说助手的公开版本化契约；原生模型历史仅保留在服务端。 */
export type ResourceKind = "novel" | "volume" | "arc" | "scene" | "chapter" | "character" | "faction" | "location" | "item" | "world_rule" | "foreshadowing" | "character_relation" | "faction_relation" | "character_faction_binding" | "character_volume_state" | "faction_volume_state";

export interface ResourceRef { resource_type: ResourceKind; id: string }
export interface ContextAttachment extends ResourceRef {
  fields: string[];
  usage: "reference" | "target";
  origin: "saved" | "draft";
  version?: number;
  text?: string;
}
export interface AssistantTurnRequest {
  message: string; attachments: ContextAttachment[]; location?: ResourceRef | null;
  writing_target?: ResourceRef | null; allow_navigation: boolean; execution_mode?: "auto" | "review";
}
export interface NavigationTarget extends ResourceRef { field?: string; deleted?: boolean }
export interface AssistantSession {
  id: string; novel_id: string; title: string; mode: "review" | "auto"; provider: string; model: string;
  archived: boolean; created_at: string; updated_at: string;
}
export interface AssistantMessage { id: string; run_id: string; role: "user" | "assistant"; content: string; attachments?: ContextAttachment[] }
export interface ChangeConfirmation { message: string; token?: string; revision?: number; conflicts?: string[]; targets: { name: string; id: string; action: ChangeOperation["action"]; fields?: Record<string, { before: unknown; after: unknown }> }[] }
export interface AssistantRun {
  id: string; session_id: string; schema_version: 1;
  creation_contract_version?: 1;
  request?: AssistantTurnRequest;
  pending_question?: { id: string; question: string; choices: string[]; target?: ResourceRef; changes: { id: string; revision: number; status: string }[]; confirmation?: ChangeConfirmation & { change_id: string } };
  status: "ready" | "running" | "waiting_approval" | "waiting_input" | "budget_exhausted" | "interrupted" | "cancelled" | "failed" | "completed";
  settings: Pick<AssistantSession, "mode" | "provider" | "model">;
  rounds: number; tool_calls: number; round_limit: number; tool_limit: number; last_event_seq: number;
  usage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  error?: { code: string; message: string };
}
export interface ChangeOperation {
  action: "create" | "update" | "delete" | "restore" | "reorder" | "status" | "preparation";
  resource_type: ResourceKind; id?: string | null; parent_id?: string | null; temporary_id?: string | null;
  fields: Record<string, unknown>; reason: string;
}
export interface ReviewIssue { severity: "conflict" | "suggestion" | "unchecked"; message: string; sources: ResourceRef[] }
export interface ChangeSet {
  id: string; schema_version: 1; revision: number; status: "draft" | "reviewed" | "applied" | "generating" | "failed" | "cancelled" | "interrupted";
  kind: "operations" | "generation" | "facts";
  confirmation?: ChangeConfirmation;
  apply_attempt?: { revision: number; outcome: "not_sent" | "unknown" | "not_committed" | "committed" }; operations?: ChangeOperation[]; candidate?: Record<string, unknown>;
  generation_task?: string; undo_of?: string;
  creation_context?: { contract_version: 1; semantics: "book_management" | "position_writing"; target?: ResourceRef; author_request_hash?: string; message_hash?: string };
  creation_error?: { code: string; message: string } | null;
  child_usage?: Record<string, { model_calls: number; usage: { input_tokens: number; output_tokens: number; total_tokens: number }; usage_complete?: boolean }>;
  program_error?: { code: string; message: string };
  diffs?: { action: ChangeOperation["action"]; resource_type: ResourceKind; id: string; reason: string; before: Record<string, unknown>; after: Record<string, unknown> }[];
  source_refs?: (ResourceRef & { version?: number; fingerprint?: string })[];
  review?: { summary: string; issues: ReviewIssue[]; revision: number; program_passed: boolean; scope_note: string; omitted_fields: string[] } | null;
  result?: { change_id: string; resume_run_id?: string | null; saved_at: string; resources: (ResourceRef & { version: number })[] };
}
export interface AssistantEvent { seq: number; event: string; data: Record<string, unknown> }
export interface SessionDetail { session: AssistantSession; messages: AssistantMessage[]; changes: ChangeSet[]; runs: AssistantRun[]; has_more: boolean; before: string | null }
export interface AssistantCapabilities { enabled: boolean; default_provider: string; providers: { id: string; model: string; supports_function_calling: boolean }[] }
export interface ResourceIndexEntry { resource_type: ResourceKind; resource_id: string; name: string; summary: string; fields: string[]; source_version: number; position: Record<string, string> }
export interface ActiveAssistantResource extends ResourceRef { name: string; version?: number; fields?: string[]; draft?: { text: string; fields: string[]; version?: number } }
