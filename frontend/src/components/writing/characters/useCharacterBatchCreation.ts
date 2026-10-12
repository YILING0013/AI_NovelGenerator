"use client";

import { useEffect, useRef, useState } from "react";
import { apiPost, ApiRequestError } from "@/lib/api";
import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { CoreCharactersResultV1, CharacterRelationsResultV1 } from "@/types/character";
import type { CharacterFactBatchCreateV1, CharacterRelationFactBatchCreateV1, CharacterFactBatchResultV1, CharacterRelationFactBatchResultV1 } from "@/types/characterFactBatch";
import type { CoreFactionsAIConfirmationRequestV2, CoreFactionsResultV2, BulkCreateCoreFactionsResponse } from "@/types/novel";
import type { CharacterRelationCandidateDraftEntry } from "./characterRelationCandidateDrafts";

interface BatchCommand<Body, Preview> {
  key: string; body: Body; preview: Preview;
  attempt?: string;
  rejected?: boolean;
  result?: unknown;
  sourceCandidate?: CharacterRelationCandidateDraftEntry;
}
export type CharacterBatchCommand = BatchCommand<CharacterFactBatchCreateV1 | CharacterRelationFactBatchCreateV1, CoreCharactersResultV1 | CharacterRelationsResultV1>;
type FactionBatchCommand = BatchCommand<CoreFactionsAIConfirmationRequestV2, CoreFactionsResultV2>;
const same = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

/** 同一 IDB 事务核对整条原命令；晚成功优先，旧页面不能删除或派发已退回的命令。 */
async function storeCommand<B, P>(scope: string, next?: BatchCommand<B, P> | null, expected?: BatchCommand<B, P> | null,
  resolution?: "dispatch" | "saved"): Promise<BatchCommand<B, P> | null> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("business_drafts", next === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore("business_drafts"), key = `${scope}:1`, request = store.get(key);
      let value: BatchCommand<B, P> | null = null;
      request.onsuccess = () => {
        const current = (request.result?.value ?? null) as BatchCommand<B, P> | null;
        value = current;
        if (next === undefined) return;
        const originalMatches = current && expected && current.key === expected.key && same(current.body, expected.body) && same(current.sourceCandidate, expected.sourceCandidate);
        if (originalMatches && current.result !== undefined && (resolution === "saved" || resolution === "dispatch")) return;
        const lateSuccess = resolution === "saved" && next?.result !== undefined && originalMatches;
        if (!same(current, expected ?? null) && !lateSuccess) { tx.abort(); return; }
        if (next === null && current?.result === undefined && !current?.rejected) { tx.abort(); return; }
        if (current?.result !== undefined && next !== null && next?.result === undefined) { tx.abort(); return; }
        if (next === null) store.delete(key);
        else store.put({ key, scope, base_version: 1, value: next, updated_at: Date.now() });
        value = next;
      };
      tx.oncomplete = () => resolve(value);
      tx.onerror = tx.onabort = () => reject(tx.error ?? new Error("另一页已处理这批保存，请重新打开查看最新结果"));
    });
  } finally { db.close(); }
}

/** 三种整批创建共用原请求存储与派发；这里不编排生成或其他业务步骤。 */
function usePersistedBatch<B, P>(novelId: string | undefined, kind: string, path: string, validate: (result: unknown, body: B) => boolean) {
  const scope = `${novelId}:character-batch:${kind}`;
  const [command, setCommand] = useState<BatchCommand<B, P> | null>(null);
  const pending = useRef<BatchCommand<B, P> | null>(null);
  const [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const running = useRef(false), epoch = useRef(0);
  useEffect(() => {
    let current = true;
    epoch.current += 1; running.current = false; setBusy(false);
    pending.current = null; setCommand(null); setReady(false); setError("");
    if (!novelId) return;
    void storeCommand<B, P>(scope).then((value) => {
      if (current) { pending.current = value; setCommand(value); setReady(true); }
    }, (failure) => { if (current) setError(String(failure)); });
    return () => { current = false; epoch.current += 1; };
  }, [scope, novelId]);

  const save = async (body: B, preview: P, onSaved: (original: BatchCommand<B, P>) => Promise<void>, sourceCandidate?: CharacterRelationCandidateDraftEntry) => {
    if (!ready || running.current || !novelId) return;
    running.current = true; setBusy(true); setError("");
    const currentEpoch = epoch.current, isCurrent = () => currentEpoch === epoch.current;
    let original = pending.current;
    const mayReject = !original || original.rejected === true;
    let sent = false;
    try {
      if (original?.result === undefined) {
        const dispatch = { ...(original ?? { key: crypto.randomUUID(), body: structuredClone(body), preview: structuredClone(preview),
          ...(sourceCandidate ? { sourceCandidate: structuredClone(sourceCandidate) } : {}) }), attempt: crypto.randomUUID(), rejected: false };
        // 每次重试都先冻结未知状态；拒绝后的超时也不能再换键。
        original = (await storeCommand(scope, dispatch, original, "dispatch"))!;
        if (!isCurrent()) return false;
        pending.current = original; setCommand(original);
      }
      if (original.result === undefined) {
        sent = true;
        const result = await apiPost<unknown>(path, original.body, { headers: { "Idempotency-Key": original.key } });
        if (!validate(result, original.body)) throw new Error("保存回复不完整，请保留这批内容并重试原请求");
        const saved = { ...original, result, rejected: false };
        if (isCurrent()) { pending.current = saved; setCommand(saved); }
        original = (await storeCommand(scope, saved, original, "saved"))!;
      } else original = (await storeCommand(scope, original, original, "saved"))!;
      if (!isCurrent()) return false;
      pending.current = original; setCommand(original);
      await onSaved(original);
      if (!isCurrent()) return false;
      await storeCommand(scope, null, original);
      if (isCurrent()) { pending.current = null; setCommand(null); }
      return isCurrent();
    } catch (failure) {
      if (isCurrent() && sent && mayReject && original && pending.current?.result === undefined && failure instanceof ApiRequestError && failure.status >= 400 && failure.status < 500) {
        const rejected = { ...original, rejected: true };
        await storeCommand(scope, rejected, original).then(() => { if (isCurrent()) { pending.current = rejected; setCommand(rejected); } }, () => undefined);
      }
      if (isCurrent()) setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally { if (isCurrent()) { running.current = false; setBusy(false); } }
  };
  const revise = async () => {
    if (!pending.current?.rejected || pending.current.result !== undefined || running.current) return false;
    try {
      await storeCommand(scope, null, pending.current);
      pending.current = null; setCommand(null); setError(""); return true;
    } catch (failure) { setError(String(failure)); return false; }
  };
  return { command, ready, busy, error, save, revise };
}

/** 人物与关系的严格整批响应核对，结果不明只保留原请求。 */
export function useCharacterBatchCreation(novelId: string | undefined, kind: "characters" | "relations") {
  return usePersistedBatch<CharacterBatchCommand["body"], CharacterBatchCommand["preview"]>(novelId, kind,
    `/api/${kind === "characters" ? "character-facts" : "character-relation-facts"}/novel/${novelId}/batch`, (value, body) => {
      const result = value as CharacterFactBatchResultV1 | CharacterRelationFactBatchResultV1 | null;
      const rows = result && ("characters" in result ? result.characters : result.relations);
      return Boolean(result && result.novel_id === novelId && Array.isArray(rows) && rows.length === body.candidates.length
        && rows.every((row, index) => row.candidate_ref === body.candidates[index].candidate_ref && typeof row.entity_id === "string"
          && typeof row.history_id === "string" && Number.isInteger(row.version) && row.version > 0)
        && (kind === "characters" ? "characters" in result && Array.isArray(result.bindings) : "relations" in result));
    });
}

/** 已触及的核心势力入口复用原命令恢复，只请求既有势力批量接口。 */
export function useFactionBatchCreation(novelId: string | undefined) {
  return usePersistedBatch<FactionBatchCommand["body"], FactionBatchCommand["preview"]>(novelId, "factions",
    `/api/factions/novel/${novelId}/bulk-core-with-relations`, (value, body) => {
      const result = value as BulkCreateCoreFactionsResponse | null;
      return Boolean(result && Array.isArray(result.factions) && Array.isArray(result.faction_relations)
        && result.faction_ref_map && body.selected_faction_refs.every((ref) => typeof result.faction_ref_map[ref] === "string")
        && result.factions.length === body.selected_faction_refs.length);
    });
}
