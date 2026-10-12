/** 势力在单卷内的参与层级。 */
export type FactionVolumeParticipationScope = "primary" | "secondary" | "background";

/** 势力在目标卷中的计划活动状态。 */
export type FactionVolumeActiveStatus = "active" | "dormant" | "dissolved";

/** 势力卷级状态允许人工编辑的正式业务字段。 */
export interface FactionVolumeStateFields {
  participation_scope: FactionVolumeParticipationScope;
  current_goal: string;
  start_state: string;
  planned_end_state: string;
  power_level: number;
  resources: string[];
  public_stance: string;
  hidden_agenda: string;
  influence_scope: string;
  active_status: FactionVolumeActiveStatus;
}

/** 势力卷级状态的公开正式响应。 */
export interface FactionVolumeStateReadV1 extends FactionVolumeStateFields {
  state_id: string;
  novel_id: string;
  volume_id: string;
  faction_id: string;
  source_state_id: string | null;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  deletion_sources: Array<"user" | "volume" | "faction">;
  created_at: string;
  updated_at: string;
}

/** 创建或更新势力卷级状态时提交的严格业务请求。 */
export type FactionVolumeStateUpsertV1 = FactionVolumeStateFields & {
  expected_version?: number;
};

/** 卷内势力卷级状态列表响应。 */
export interface FactionVolumeStateListV1 {
  data: FactionVolumeStateReadV1[];
}

/** 从上一正式卷初始化选中势力的请求。 */
export interface FactionVolumeStateInitializeV1 {
  faction_ids: string[];
  skip_existing: false;
}

/** 从上一正式卷初始化后的正式响应。 */
export interface FactionVolumeStateInitializeResultV1 {
  source_volume_id: string;
  target_volume_id: string;
  states: FactionVolumeStateReadV1[];
}

/** 势力卷级状态永久删除响应。 */
export interface FactionVolumeStateHardDeleteV1 {
  deleted: true;
  state_id: string;
}
