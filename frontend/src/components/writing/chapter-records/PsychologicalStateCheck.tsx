"use client";

import { Button } from "@heroui/react";
import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { useTranslations } from "next-intl";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { TaskFlowForm, TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import type { ChapterCharacterRelationCheckResultV2, ChapterCharacterRelationCheckResult, ChapterItemOwnerCheckResult, ChapterPsychologicalCheckResultV1, ChapterPsychologicalCheckSourceV1, ChapterWorldRulesCheckResultV1 } from "@/types/chapterRecords";
import type { ChapterCharacterRelationCheck, ChapterItemOwnerCheck, ChapterRecordDraft, ChapterPsychologicalCheck, ChapterWorldRulesCheck } from "./chapterRecordDrafts";

import { WorldRuleCheckResult } from "./WorldRuleCheckReview";

type Check = ChapterPsychologicalCheck | ChapterItemOwnerCheck | ChapterCharacterRelationCheck | ChapterWorldRulesCheck;
type CheckProps = {
  novelId: string;
  draft: ChapterRecordDraft;
  source: ChapterPsychologicalCheckSourceV1 | null;
  blocked: boolean;
  cancelRef: RefObject<(() => void) | null>;
} & ({
  mode?: "psychological-state";
  onCheck: (check: ChapterPsychologicalCheck) => Promise<unknown>;
  onAdopt: (check: ChapterPsychologicalCheck) => void;
} | {
  mode: "item-owner";
  onCheck: (check: ChapterItemOwnerCheck) => Promise<unknown>;
  onAdopt: (check: ChapterItemOwnerCheck) => void;
} | {
  mode: "world-rules";
  onCheck: (check: ChapterWorldRulesCheck) => Promise<unknown>;
  onAdopt: (check: ChapterWorldRulesCheck) => void;
} | {
  mode: "character-relation-state";
  onCheck: (check: ChapterCharacterRelationCheck) => Promise<unknown>;
  onAdopt: (check: ChapterCharacterRelationCheck) => void;
});

/** 功能：在原确认稿中检查整章，审阅心理、持有人或关系现状建议。Args: props 当前稿、已核验修订、固定检查种类和原稿回调。Returns: 同一弹窗内的检查表单和结果。 */
export default function PsychologicalStateCheck(props: CheckProps) {
  const { novelId, draft, source, blocked, cancelRef } = props;
  const active = useContext(RetainedViewActive);
  const activeRef = useRef(active); activeRef.current = active;
  const worldRulesMode = props.mode === "world-rules";
  const itemOwnerMode = props.mode === "item-owner";
  const relationMode = props.mode === "character-relation-state";
  const itemFactsMode = itemOwnerMode && draft.itemCheckVersion === 2;
  const relationFactsMode = relationMode && draft.relationCheckVersion === 2;
  // 各模式回调只接收各自模式的检查；下面共用执行、取消和本地保存流程。
  const onCheck = props.onCheck as (check: Check) => Promise<unknown>;
  const onAdopt = props.onAdopt as (check: Check) => void;
  const check = worldRulesMode ? draft.worldRuleCheck : relationMode ? draft.relationCheck : itemOwnerMode ? draft.itemOwnerCheck : draft.check;
  const target = worldRulesMode ? draft.worldRuleTarget : relationMode ? draft.relationTarget : itemOwnerMode ? draft.itemOwner : draft.targetState;
  const targetReady = Boolean(target && (!("rules" in target) || target.rules.length >= 1 && target.rules.length <= 5) && (!("item_id" in target) || target.from_character_id && target.to_character_id && target.from_character_id !== target.to_character_id));
  const t = useTranslations(worldRulesMode ? "writing.chapterRecords.worldRuleCheck" : relationMode ? "writing.chapterRecords.relationCheck" : itemOwnerMode ? "writing.chapterRecords.itemOwnerCheck" : "writing.chapterRecords.check");
  const relationFactT = useTranslations("writing.characterRelationFacts");
  const flow = useTaskFlow(worldRulesMode ? "check_chapter_world_rules_by_ai" : relationFactsMode ? "check_chapter_character_relation_facts_by_ai" : relationMode ? "check_chapter_character_relation_state_by_ai" : itemFactsMode ? "check_chapter_item_owner_facts_by_ai" : itemOwnerMode ? "check_chapter_item_owner_by_ai" : "check_chapter_psychological_state_by_ai");
  const [running, setRunning] = useState(false);
  const [restored, setRestored] = useState(!check);
  const setupToRestore = useRef(check?.setup);
  const token = useRef(0);
  const mounted = useRef(true);
  const errorRef = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const current = useRef({ check, target, source, blocked, onCheck });
  current.current = { check, target, source, blocked, onCheck };
  const { loading, select, setInputs, setParams, discard } = flow;
  const sourceIdentity = source ? `${source.chapter_id}:${source.revision_id}:${source.version}:${source.content_hash}` : "";
  const targetIdentity = target ? "rules" in target ? JSON.stringify(target.rules.map((rule) => [rule.rule_id, rule.version])) : "item_id" in target
    ? `${target.item_id}:${target.version}:${target.from_character_id}:${target.to_character_id}`
    : "relation_id" in target ? `${target.entity_id ?? ""}:${target.relation_id}:${target.version}:${target.source_character_id}:${target.target_character_id}`
      : `${target.state_id}:${target.version}` : "";
  const checkedTargetIdentity = check ? "rules" in check.target ? JSON.stringify(check.target.rules.map((rule) => [rule.rule_id, rule.version])) : "item_id" in check.target
    ? `${check.target.item_id}:${check.target.version}:${check.target.from_character_id}:${check.target.to_character_id}`
    : "relation_id" in check.target ? `${check.target.entity_id ?? ""}:${check.target.relation_id}:${check.target.version}:${check.target.source_character_id}:${check.target.target_character_id}`
      : `${check.target.state_id}:${check.target.version}` : "";

  useEffect(() => {
    if (loading || !setupToRestore.current) return;
    const setup = setupToRestore.current;
    setupToRestore.current = undefined;
    void select(setup.flow_ref).then(() => {
      if (mounted.current) { setInputs(setup.inputs); setParams(setup.params); setRestored(true); }
    });
  }, [loading, select, setInputs, setParams]);

  useEffect(() => {
    mounted.current = true;
    const cancel = () => {
      token.current += 1;
      controller.current?.abort(); controller.current = null;
      setRunning(false); void discard();
      const check = current.current.check;
      if (check?.status === "running" && !current.current.blocked) {
        void current.current.onCheck({ ...check, status: "interrupted" }).catch(() => {});
      }
    };
    cancelRef.current = cancel;
    return () => { mounted.current = false; token.current += 1; controller.current?.abort(); cancelRef.current = null; };
  }, [cancelRef, discard]);

  useEffect(() => {
    if (controller.current) cancelRef.current?.();
  }, [sourceIdentity, targetIdentity, draft.key, itemOwnerMode, itemFactsMode, relationMode, relationFactsMode, worldRulesMode, blocked, active, cancelRef]);

  useEffect(() => {
    if (!active || !check?.error) return;
    const frame = requestAnimationFrame(() => errorRef.current?.querySelector<HTMLElement>("[role='alert']")?.focus());
    return () => cancelAnimationFrame(frame);
  }, [active, check?.error]);
  const inputsMatch = Boolean(check && source && check.source.chapter_id === source.chapter_id && check.source.revision_id === source.revision_id && check.source.version === source.version && check.source.content_hash === source.content_hash
    && checkedTargetIdentity === targetIdentity);

  const generate = async (retry = false) => {
    const now = current.current;
    if (!activeRef.current || controller.current || now.blocked || !now.source || !now.target || !targetReady || !restored || flow.loading || !flow.definition) return;
    token.current += 1; const runToken = token.current;
    const abort = new AbortController(); controller.current = abort;
    setRunning(true);
    const pending = {
      source: now.source, target: now.target,
      setup: retry && inputsMatch && now.check ? now.check.setup : flow.resolveSetup(),
      status: "running", result: null, error: "",
    } as Check;
    try {
      // 检查输入先落在原稿，生成结果只合入当前稿的 check，不覆盖作者等待时的新输入。
      await onCheck(pending);
      if (runToken !== token.current || abort.signal.aborted) return;
      await discard();
      const scope = "rules" in pending.target ? { source: pending.source, rules: pending.target.rules.map((rule) => ({ rule_id: rule.rule_id, expected_version: rule.version })) } : "item_id" in pending.target ? {
        source: pending.source, item_id: pending.target.item_id, expected_version: pending.target.version,
        from_character_id: pending.target.from_character_id, to_character_id: pending.target.to_character_id,
      } : "relation_id" in pending.target ? {
        source: pending.source, relation_id: pending.target.relation_id, expected_version: pending.target.version,
      } : {
        source: pending.source, state_id: pending.target.state_id, expected_version: pending.target.version,
      };
      const generated = await flow.run(`/api/chapter-records/novel/${novelId}/${worldRulesMode ? "world-rules" : relationFactsMode ? "character-relation-facts" : relationMode ? "character-relation-state" : itemFactsMode ? "item-facts" : itemOwnerMode ? "item-owner" : "psychological-state"}/check`, scope, abort.signal, false, pending.setup);
      if (runToken !== token.current || abort.signal.aborted) return;
      const result = generated.result as ChapterPsychologicalCheckResultV1 | ChapterItemOwnerCheckResult | ChapterCharacterRelationCheckResult | ChapterWorldRulesCheckResultV1;
      const input = result?.basis?.flow_snapshot?.business_input;
      if (!input || input.novel_id !== novelId || input.source.chapter_id !== pending.source.chapter_id
        || input.source.revision_id !== pending.source.revision_id || input.source.version !== pending.source.version || input.source.content_hash !== pending.source.content_hash
        || !result.candidate || !Array.isArray(result.candidate.issues)) throw new Error(t("invalidResult"));
      if ("rules" in pending.target) {
        const selectedRules = pending.target.rules;
        if (!("rules" in input) || JSON.stringify(input.rules) !== JSON.stringify(scope.rules)
          || !("checked_rules" in result) || result.checked_rules.length !== pending.target.rules.length
          || !result.checked_rules.every((rule, index) => rule.entity_id && rule.novel_id === novelId && !rule.is_deleted && rule.status === "active" && rule.scope_type === "global"
            && rule.rule_id === selectedRules[index].rule_id && rule.version === selectedRules[index].version)
          || !result.candidate.issues.every((issue) => typeof issue === "object" && issue !== null && typeof issue.text === "string"
            && Array.isArray(issue.rule_ids) && issue.rule_ids.length > 0 && issue.rule_ids.every((id) => result.checked_rules.some((rule) => rule.rule_id === id)))) throw new Error(t("invalidResult"));
      } else if (!("expected_version" in input) || input.expected_version !== pending.target.version) throw new Error(t("invalidResult"));
      else if ("item_id" in pending.target) {
        if (!("item_id" in input) || input.item_id !== pending.target.item_id
          || input.from_character_id !== pending.target.from_character_id || input.to_character_id !== pending.target.to_character_id) throw new Error(t("invalidResult"));
        if (itemFactsMode && (!("checked_facts" in result) || result.schema_version !== 2 || result.workflow !== "check_chapter_item_owner_facts_by_ai"
          || result.checked_facts.position.intent !== "chapter_before" || result.checked_facts.position.target_id !== pending.source.chapter_id
          || !("check_target" in result) || !("item_id" in result.check_target) || result.check_target.item_id !== pending.target.item_id)) throw new Error(t("invalidResult"));
      } else if ("relation_id" in pending.target) {
        const checked = "check_target" in result ? result.check_target : null;
        if (!("relation_id" in input) || input.relation_id !== pending.target.relation_id
          || !checked || !("relation_id" in checked) || !checked.entity_id
          || checked.relation_id !== pending.target.relation_id || checked.expected_version !== pending.target.version
          || checked.source_character_id !== pending.target.source_character_id || checked.target_character_id !== pending.target.target_character_id
          || pending.target.entity_id && checked.entity_id !== pending.target.entity_id) throw new Error(t("invalidResult"));
        if (relationFactsMode) {
          if (!("checked_facts" in result) || result.schema_version !== 2 || result.workflow !== "check_chapter_character_relation_facts_by_ai"
            || result.checked_facts.position.target_id !== pending.source.chapter_id || result.checked_facts.position.intent !== "chapter_before"
            || result.checked_facts.position.target_type !== "chapter"
            || (typeof (result as ChapterCharacterRelationCheckResultV2).checked_facts.values.current_state !== "string" && !(result as ChapterCharacterRelationCheckResultV2).checked_facts.unknown.current_state)) throw new Error(t("invalidResult"));
        } else if (!("current_state" in checked) || checked.current_state !== pending.target.current_state || "checked_facts" in result) throw new Error(t("invalidResult"));
      } else if (!("state_id" in input) || input.state_id !== pending.target.state_id
        || !("check_target" in result) || !result.check_target || !("state_id" in result.check_target) || result.check_target.state_id !== pending.target.state_id
        || result.check_target.expected_version !== pending.target.version) throw new Error(t("invalidResult"));
      // 原稿已保留内存结果并显示保存错误，可导出或关闭保稿重试；不要改成生成失败。
      await current.current.onCheck({ ...pending, status: "done", result, ...(worldRulesMode ? { issueEdits: (result as ChapterWorldRulesCheckResultV1).candidate.issues.map((issue) => ({ text: issue.text, selected: false, rejected: false, appended: false })) } : {}) } as Check).catch(() => {});
    } catch (failure) {
      if (runToken === token.current && !abort.signal.aborted) {
        await current.current.onCheck({ ...pending, status: "failed", error: failure instanceof Error ? failure.message : t("failed") }).catch(() => {});
      }
    } finally {
      // 同一目标取消后立即重试，旧请求的 finally 也不能关掉新进度。
      if (runToken === token.current) { controller.current = null; setRunning(false); }
    }
  };

  return <section aria-label={t("title")} className="grid min-w-0 gap-3 border-t border-border pt-4">
    <h4 className="text-sm font-semibold">{t("title")}</h4>
    <TaskFlowForm flow={{ ...flow, flows: flow.flows.map((item) => item.id === `default_${flow.task}` ? { ...item, name: t("defaultFlow") } : item) }} disabled={blocked || running || !restored} showError={!check?.error} />
    {(!source || !targetReady) && <p role="status" className="text-sm text-muted">{t("selectInputs")}</p>}
    {check?.error && <div ref={errorRef}><RelationEditorErrorSummary message={check.error} /></div>}
    {check?.status === "interrupted" && <p role="status" className="text-sm">{t("interrupted")}</p>}
    {check && !inputsMatch && <p role="status" className="text-sm text-muted">{t("inputsChanged")}</p>}
    <div className="flex flex-wrap gap-2">
      {/* pending 禁止重复执行但保留焦点，让 Escape 继续交给原 Modal。 */}
      <Button variant="outline" isPending={running} isDisabled={!active || blocked || !source || !targetReady || flow.loading || !flow.definition || !restored} onPress={() => void generate()}>{t("generate")}</Button>
      {running && <Button variant="ghost" onPress={() => cancelRef.current?.()}>{t("cancel")}</Button>}
      {check && ["failed", "interrupted"].includes(check.status) && <Button variant="outline" isDisabled={!active || blocked || running || !inputsMatch || !targetReady || !restored || flow.loading} onPress={() => void generate(true)}>{t("retry")}</Button>}
    </div>
    {(running || check?.status === "failed") && <TaskFlowProgress flow={flow} running={running} failed={check?.status === "failed"} />}
    {worldRulesMode && check?.result && <WorldRuleCheckResult check={check as ChapterWorldRulesCheck} blocked={blocked || running} inputsMatch={inputsMatch} onCheck={onCheck} onAdopt={onAdopt} />}
    {!worldRulesMode && check?.result && !("checked_rules" in check.result) && <div className="grid min-w-0 gap-3" data-testid={relationMode ? "character-relation-check-result" : itemOwnerMode ? "item-owner-check-result" : "psychological-check-result"}>
      {relationFactsMode && "checked_facts" in check.result && <div><h5 className="mb-1 text-xs font-medium text-muted">{t("beforeFacts")}</h5><p className="reading-copy whitespace-pre-wrap">{(check.result as ChapterCharacterRelationCheckResultV2).checked_facts.values.current_state ?? relationFactT(`unknown.${(check.result as ChapterCharacterRelationCheckResultV2).checked_facts.unknown.current_state}`)}</p></div>}
      <div><h5 className="mb-1 text-xs font-medium text-muted">{t("issues")}</h5>
        {check.result.candidate.issues.length ? <ul className="list-inside list-disc space-y-2">{check.result.candidate.issues.map((issue, index) => <li key={index} className="reading-copy whitespace-pre-wrap">{issue}</li>)}</ul> : <p className="text-sm text-muted">{t("noIssues")}</p>}
      </div>
      {check.result.candidate.suggestion ? <>
        {"psychological_state" in check.result.candidate.suggestion && <div><h5 className="mb-1 text-xs font-medium text-muted">{t("suggestion")}</h5><p className="reading-copy whitespace-pre-wrap">{check.result.candidate.suggestion.psychological_state || t("emptyValue")}</p></div>}
        {"current_state" in check.result.candidate.suggestion && <div><h5 className="mb-1 text-xs font-medium text-muted">{t("suggestion")}</h5><p className="reading-copy whitespace-pre-wrap">{check.result.candidate.suggestion.current_state}</p></div>}
        <div><h5 className="mb-1 text-xs font-medium text-muted">{t("quote")}</h5><p className="reading-copy whitespace-pre-wrap">{check.result.candidate.suggestion.quote}</p></div>
        <p className="text-sm text-muted">{t("reviewRisk")}</p>
        {check.status === "done" && <div className="flex flex-wrap gap-2">
          <Button variant="outline" isDisabled={blocked || !inputsMatch} onPress={() => onAdopt(check)}>{t(relationFactsMode ? "prepare" : "adopt")}</Button>
          <Button variant="ghost" isDisabled={blocked} onPress={() => { void onCheck({ ...check, status: "rejected" }).catch(() => {}); }}>{t("reject")}</Button>
        </div>}
        {["adopted", "rejected"].includes(check.status) && <p role="status" className="text-sm">{t(check.status)}</p>}
      </> : <p role="status" className="text-sm">{t("noSuggestion")}</p>}
    </div>}
  </section>;
}
