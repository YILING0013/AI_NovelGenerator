/** 角色在单卷内的参与层级。 */
export type CharacterVolumeParticipationScope = "primary" | "secondary" | "background";

/** 本卷参与和计划的六个字段，不包含人物实际处境。 */
export interface CharacterVolumePlanFieldsV1 {
  participation_scope: CharacterVolumeParticipationScope;
  current_goal: string;
  start_state: string;
  planned_end_state: string;
  relationship_focus_ids: string[];
  arc_progress: number;
}

/** 新建本卷参与计划的 HTTP 请求。 */
export type CharacterVolumePlanCreateV1 = Pick<CharacterVolumePlanFieldsV1,
  "participation_scope" | "current_goal" | "start_state"
> & Partial<Pick<CharacterVolumePlanFieldsV1,
  "planned_end_state" | "relationship_focus_ids" | "arc_progress"
>> & {
  volume_id: string;
  character_id: string;
};

/** 只更新实际修改的计划字段，保留作者开始编辑时的版本。 */
export type CharacterVolumePlanUpdateV1 = Partial<CharacterVolumePlanFieldsV1> & {
  expected_version: number;
};

/** 旧完整状态形状用于读取和原候选恢复；三个旧处境字段不作为事实来源。 */
export interface CharacterVolumeStateFields extends CharacterVolumePlanFieldsV1 {
  psychological_state: string;
  public_state: string;
  hidden_state: string;
}

/** 角色卷级状态的公开正式响应。 */
export interface CharacterVolumeStateReadV1 extends CharacterVolumeStateFields {
  state_id: string;
  novel_id: string;
  volume_id: string;
  character_id: string;
  source_state_id: string | null;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  deletion_sources: Array<"user" | "volume" | "character">;
  created_at: string;
  updated_at: string;
}

/** 创建或更新角色卷级状态时提交的严格业务请求。 */
export type CharacterVolumeStateUpsertV1 = CharacterVolumeStateFields & {
  expected_version?: number;
};

/** 卷内角色卷级状态列表响应。 */
export interface CharacterVolumeStateListV1 {
  data: CharacterVolumeStateReadV1[];
}

/** 从上一正式卷初始化选中角色的请求。 */
export interface CharacterVolumeStateInitializeV1 {
  character_ids: string[];
  skip_existing: false;
}

/** 从上一正式卷初始化后的正式响应。 */
export interface CharacterVolumeStateInitializeResultV1 {
  source_volume_id: string;
  target_volume_id: string;
  states: CharacterVolumeStateReadV1[];
}

/** 角色卷级状态永久删除响应。 */
export interface CharacterVolumeStateHardDeleteV1 {
  deleted: true;
  state_id: string;
}
