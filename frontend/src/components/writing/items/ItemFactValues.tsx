"use client";

import { useTranslations } from "next-intl";
import type { ItemFactValuesV1 } from "@/types/itemFacts";
import { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";

export interface ItemFactChoices {
  characters: readonly { character_id: string; name: string; status: string; is_deleted: boolean }[];
  factions: readonly { faction_id: string; name: string; active_status: string; is_deleted: boolean }[];
  locations: readonly { location_id: string; name: string; status: string; is_deleted: boolean }[];
}

/** 功能：确认前校验完整四项组合，设计字段编辑不调用。Args: 状态及当前引用清单。Returns: 是否可以准备保存。 */
export function validItemFactValues(value: ItemFactValuesV1, choices: ItemFactChoices): boolean {
  if (!["available", "held", "lost", "destroyed", "consumed"].includes(value.lifecycle_status)) return false;
  if (value.lifecycle_status === "held" && !value.owner_character_id && !value.controlling_faction_id) return false;
  if (["destroyed", "consumed"].includes(value.lifecycle_status)) return !value.owner_character_id && !value.controlling_faction_id && !value.current_location_id;
  return (!value.owner_character_id || choices.characters.some((row) => row.character_id === value.owner_character_id && !row.is_deleted && row.status === "active"))
    && (!value.controlling_faction_id || choices.factions.some((row) => row.faction_id === value.controlling_faction_id && !row.is_deleted && row.active_status === "active"))
    && (!value.current_location_id || choices.locations.some((row) => row.location_id === value.current_location_id && !row.is_deleted && row.status === "active"));
}

/** 功能：显示或填写物品完整状态，未知时不拿裸资料补值。Args: 完整组、引用选项和可选修改回调。Returns: 四项状态。 */
export default function ItemFactValues({ value, choices, onChange, disabled = false, ownerOnly = false }: {
  value: ItemFactValuesV1 | null; choices: ItemFactChoices; onChange?: (value: ItemFactValuesV1) => void; disabled?: boolean; ownerOnly?: boolean;
}) {
  const t = useTranslations("writing.items");
  const f = useTranslations("writing.itemFacts");
  if (!value) return <p className="text-sm text-muted">{f("unknown")}</p>;
  const refs = [
    { field: "owner_character_id" as const, label: t("fields.owner"), rows: choices.characters.map((row) => ({ id: row.character_id, name: row.name, active: row.status === "active" && !row.is_deleted })) },
    { field: "controlling_faction_id" as const, label: t("fields.faction"), rows: choices.factions.map((row) => ({ id: row.faction_id, name: row.name, active: row.active_status === "active" && !row.is_deleted })) },
    { field: "current_location_id" as const, label: t("fields.location"), rows: choices.locations.map((row) => ({ id: row.location_id, name: row.name, active: row.status === "active" && !row.is_deleted })) },
  ];
  return <div className="grid min-w-0 gap-4 detail-fields">
    <label className="grid gap-2 text-xs font-medium text-muted">{t("fields.status")}{onChange ? <select className={INPUT} value={value.lifecycle_status} disabled={disabled || ownerOnly} onChange={(event) => {
      const status = event.target.value as ItemFactValuesV1["lifecycle_status"];
      onChange({ ...value, lifecycle_status: status, ...(["destroyed", "consumed"].includes(status) ? { owner_character_id: null, controlling_faction_id: null, current_location_id: null } : {}) });
    }}>{(["available", "held", "lost", "destroyed", "consumed"] as const).map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}</select> : <span className="text-sm font-normal text-foreground">{t(`status.${value.lifecycle_status}`)}</span>}</label>
    {refs.map(({ field, label, rows }) => <label key={field} className="grid min-w-0 gap-2 text-xs font-medium text-muted">{label}{onChange ? <select className={INPUT} value={value[field] ?? ""} disabled={disabled || ownerOnly || ["destroyed", "consumed"].includes(value.lifecycle_status)} onChange={(event) => onChange({ ...value, [field]: event.target.value || null })}>
      <option value="">{f("none")}</option>{rows.filter((row) => row.active || row.id === value[field]).map((row) => <option key={row.id} value={row.id} disabled={!row.active}>{row.name}{!row.active ? ` · ${f("unavailable")}` : ""}</option>)}
      {value[field] && !rows.some((row) => row.id === value[field]) && <option value={value[field]!} disabled>{value[field]} · {f("unavailable")}</option>}
    </select> : <span className="break-words text-sm font-normal text-foreground">{rows.find((row) => row.id === value[field])?.name ?? value[field] ?? f("none")}</span>}</label>)}
  </div>;
}
