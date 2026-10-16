"""小说正式聚合、封面资产与级联删除的领域服务。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Mapping
from typing import Any

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import (
    DuplicateKeyError,
    IdempotencyConflictError,
    NotFoundError,
    TransactionNotSupportedError,
    VersionConflictError,
)
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import (
    build_idempotency_fingerprint,
    resolve_idempotent_replay,
    validate_expected_version,
)
from backend.services.llm.candidate_contract import (
    CandidateBasisV1,
    require_current_candidate_basis,
)
from backend.services.llm.novel_generation_contract import (
    AI_CREATE_FINAL_STEP,
    AI_CREATE_SCHEMA_ID,
    AI_CREATE_SCHEMA_VERSION,
    AI_CREATE_WORKFLOW,
    NOVEL_REWRITE_SCHEMA_ID,
    NOVEL_REWRITE_SCHEMA_VERSION,
    NOVEL_REWRITE_STEP,
    NOVEL_REWRITE_WORKFLOW,
    NovelFieldRewriteCandidateV1,
    NovelFieldRewriteGenerationInputV1,
    compute_ai_create_input_fingerprint,
    compute_novel_rewrite_input_fingerprint,
)
from backend.services.novel.cover_asset import (
    EncodedCoverAsset,
    cover_asset_write_lock,
    remove_cover_asset,
    store_cover_asset,
)
from backend.services.novel.chapter_record_contract import ChapterRecordDeleteCountsV1
from backend.services.novel.chapter_record_source import RECORD_COLLECTIONS, count_novel_chapter_records


logger = logging.getLogger(__name__)


async def _update_novel_fields(novel: dict[str, Any], fields: dict[str, Any], *, session: Any = None) -> dict[str, Any] | None:
    """人工和 AI 改名共用事务，只有原本有效的剧情随新书名保留依据。"""
    renamed = "title" in fields and fields["title"] != novel.get("title")
    if renamed:
        from backend.services.novel.writing_context import writing_content
        before, after = writing_content(novel, "novel"), writing_content({**novel, **fields}, "novel")
        before.pop("title", None)
        after.pop("title", None)
        # 同时修改真实剧情输入时不保留依据，也不需要跨集合改写。
        renamed = before == after

    async def write(active_session):
        updated = await novel_repo.update_versioned_novel(str(novel["_id"]), novel["version"], fields, is_deleted=False, session=active_session)
        if updated is not None and renamed:
            from backend.services.novel.plot_service import preserve_plots_after_novel_rename
            await preserve_plots_after_novel_rename(novel, updated, session=active_session)
        return updated

    if renamed and session is None:
        return await run_mongo_write_unit(write, "rename_novel", require_transaction=True)
    return await write(session)


NOVEL_EDITABLE_FIELDS = frozenset(
    {
        "title",
        "subtitle",
        "genre",
        "tags",
        "introduction",
        "summary",
        "core_seed",
        "worldview",
        "writing_style",
        "narrative_pov",
        "era_background",
        "plot",
        "tone",
        "target_audience",
        "core_idea",
        "number_of_chapters",
        "words_per_chapter",
    }
)


def _plain_dict(value: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    """把严格请求模型或映射转换为独立普通字典。

    Args:
        value: Pydantic 请求模型或映射。
        exclude_unset: 是否只保留调用方显式提交的字段。

    Returns:
        可安全过滤和计算请求摘要的字典。
    """
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(mode="json", exclude_unset=exclude_unset))
    raise TypeError("小说请求必须是映射或 Pydantic 模型")


def _prepare_novel_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    """过滤并规范化小说人工字段，不接受封面和审计旁路。

    Args:
        source: 已通过 API Schema 的候选或人工字段。

    Returns:
        可持久化的小说业务字段。
    """
    prepared = {key: value for key, value in source.items() if key in NOVEL_EDITABLE_FIELDS}
    if "title" in prepared:
        prepared["title"] = str(prepared["title"]).strip()
        if not prepared["title"]:
            raise ValueError("小说标题不能为空")
    if "genre" in prepared:
        prepared["genre"] = str(prepared["genre"]).strip()
        if not prepared["genre"]:
            raise ValueError("小说类型不能为空")
    if "tags" in prepared:
        tags: list[str] = []
        for raw_tag in prepared["tags"]:
            tag = str(raw_tag).strip()
            if tag and tag not in tags:
                tags.append(tag)
        prepared["tags"] = tags
    return prepared


class NovelService:
    """统一编排小说的创建、查询、CAS 生命周期和封面写入。"""

    @staticmethod
    async def _create_idempotent(
        document: Mapping[str, Any],
        *,
        request_payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """以目标小说文档内指纹实现创建幂等与并发回放。"""
        fingerprint = build_idempotency_fingerprint(idempotency_key, request_payload)

        async def find_replay(session: Any) -> dict[str, Any] | None:
            existing = await novel_repo.find_by_creation_idempotency(
                fingerprint.key_hash,
                session=session,
            )
            return resolve_idempotent_replay(
                existing,
                fingerprint.request_hash,
                label="小说创建",
            )

        async def create(session: Any) -> dict[str, Any]:
            replay = await find_replay(session)
            if replay is not None:
                return replay
            novel_document = {
                **document,
                **fingerprint.as_creation_fields(),
                "version": 1,
                "status": "draft",
                "current_volume_count": 0,
                "current_chapter_count": 0,
                "current_word_count": 0,
            }
            novel_id = await novel_repo.create_novel(novel_document, session=session)
            return await novel_repo.get_novel_by_id(novel_id, session=session)

        try:
            return await run_mongo_write_unit(create, "create_novel")
        except DuplicateKeyError:
            # 唯一索引输家只回放同键同载荷；异载荷仍由公共 helper 返回 409。
            replay = await find_replay(None)
            if replay is not None:
                return replay
            raise

    @staticmethod
    async def create_manual_novel(
        request: Any,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """创建一本文档字段完全由用户确认的小说。

        Args:
            request: 严格人工创建请求。
            idempotency_key: 必填的 Idempotency-Key 原文。

        Returns:
            首次创建或幂等回放的小说 BSON 文档。
        """
        payload = _plain_dict(request)
        payload.setdefault("request_type", "manual")
        document = _prepare_novel_fields(payload)
        return await NovelService._create_idempotent(
            document,
            request_payload=payload,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    async def create_ai_novel(
        request: Any,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """复核 AI 新书候选依据后执行唯一一次正式写入。

        Args:
            request: 含 candidate、basis、generation_input 和空版本表的严格确认信封。
            idempotency_key: 必填的 Idempotency-Key 原文。

        Returns:
            首次创建或幂等回放的小说 BSON 文档。
        """
        payload = _plain_dict(request)
        idempotency = build_idempotency_fingerprint(idempotency_key, payload)
        existing = await novel_repo.find_by_creation_idempotency(
            idempotency.key_hash,
        )
        replay = resolve_idempotent_replay(
            existing,
            idempotency.request_hash,
            label="小说创建",
        )
        if replay is not None:
            # 首次确认已经成功后，Prompt/Provider 漂移不能破坏同请求的幂等回放。
            return replay
        basis = CandidateBasisV1.model_validate(payload["basis"])
        if (
            basis.novel_id is not None
            or basis.workflow != AI_CREATE_WORKFLOW
            or basis.step != AI_CREATE_FINAL_STEP
            or basis.schema_id != AI_CREATE_SCHEMA_ID
            or basis.schema_version != AI_CREATE_SCHEMA_VERSION
            or basis.source_refs
        ):
            raise DomainApiError(
                "CANDIDATE_BASIS_INVALID",
                "AI 新书候选依据与当前工作流不匹配",
                status_code=422,
            )
        if payload.get("expected_versions"):
            raise DomainApiError(
                "CANDIDATE_VERSIONS_INVALID",
                "AI 新书确认不能携带尚不存在的正式资源版本",
                status_code=422,
            )

        # 生成与确认共用无 Router 依赖的函数，完整覆盖 Prompt、Schema、Provider/model 和六参数。
        try:
            current_fingerprint = compute_ai_create_input_fingerprint(
                payload["generation_input"],
                flow_snapshot=basis.flow_snapshot,
            )
        except ValueError as exc:
            raise DomainApiError(
                "CANDIDATE_FINGERPRINT_CONFLICT",
                "AI 新书候选的生成配置已变化，请重新生成",
                status_code=409,
            ) from exc
        if basis.input_fingerprint != current_fingerprint:
            raise DomainApiError(
                "CANDIDATE_FINGERPRINT_CONFLICT",
                "AI 新书候选输入或当前生成配置已变化，请重新生成",
                status_code=409,
            )

        document = _prepare_novel_fields(dict(payload["candidate"]))
        return await NovelService._create_idempotent(
            document,
            request_payload=payload,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    async def confirm_ai_field(
        novel_id: str,
        request: Any,
        *,
        idempotency_key: str,
        session: Any = None,
    ) -> dict[str, Any]:
        """复核保存态字段候选并以幂等 CAS 只写目标字段。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            request: 严格字段候选确认信封。
            idempotency_key: 必填的确认幂等键。
            session: 调用方事务；提供时不另开事务。

        Returns:
            首次确认或同载荷回放后的小说文档。
        """
        payload = _plain_dict(request)
        candidate = NovelFieldRewriteCandidateV1.model_validate(payload["candidate"])
        basis = CandidateBasisV1.model_validate(payload["basis"])
        generation_input = NovelFieldRewriteGenerationInputV1.model_validate(
            payload["generation_input"]
        )
        fingerprint = build_idempotency_fingerprint(idempotency_key, payload)
        novel = await novel_repo.get_novel_by_id(novel_id, session=session)
        receipts = dict(novel.get("ai_field_confirmation_receipts", {}))

        if fingerprint.key_hash in receipts:
            if receipts[fingerprint.key_hash] != fingerprint.request_hash:
                raise IdempotencyConflictError(
                    "同一 Idempotency-Key 已用于不同的小说字段确认请求"
                )
            # 收据表示该命令已经成功；后续合法编辑不能让原命令再次执行。
            return novel

        current_version = int(novel["version"])
        expected_key = f"novel:{novel_id}"
        if payload["expected_versions"] != {expected_key: current_version}:
            raise VersionConflictError(
                "expected_versions 必须且只能携带当前小说精确版本"
            )
        if generation_input.novel_id != novel_id:
            raise DomainApiError(
                "CANDIDATE_INPUT_INVALID",
                "字段候选 generation_input 与当前小说不匹配",
                status_code=422,
            )
        if (
            basis.novel_id != novel_id
            or basis.workflow != NOVEL_REWRITE_WORKFLOW
            or basis.step != NOVEL_REWRITE_STEP
            or basis.schema_id != NOVEL_REWRITE_SCHEMA_ID
            or basis.schema_version != NOVEL_REWRITE_SCHEMA_VERSION
            or len(basis.source_refs) != 1
            or basis.source_refs[0].resource_type != "novel"
            or basis.source_refs[0].id != novel_id
        ):
            raise DomainApiError(
                "CANDIDATE_BASIS_INVALID",
                "字段候选依据与当前小说或工作流不匹配",
                status_code=422,
            )
        if candidate.target_field != generation_input.target_field:
            raise DomainApiError(
                "CANDIDATE_TARGET_INVALID",
                "字段候选回显目标与 generation_input 不一致",
                status_code=422,
            )

        try:
            current_fingerprint = compute_novel_rewrite_input_fingerprint(
                generation_input,
                novel=novel,
                flow_snapshot=basis.flow_snapshot,
            )
        except ValueError as exc:
            # 合法候选生成后 Provider/model 配置被移除属于候选失效，不是字段请求格式错误。
            raise DomainApiError(
                "CANDIDATE_FINGERPRINT_CONFLICT",
                "字段候选的生成配置已变化，请重新生成",
                status_code=409,
            ) from exc
        require_current_candidate_basis(
            basis,
            current_source_versions={("novel", novel_id): current_version},
            current_fingerprint=current_fingerprint,
        )
        await NovelService._get_versioned_novel(novel_id, current_version, deleted=False, session=session)
        fields = _prepare_novel_fields(
            {candidate.target_field: candidate.value}
        )
        updated = await _update_novel_fields(
            novel,
            {
                **fields,
                "ai_field_confirmation_receipts": {
                    **receipts,
                    fingerprint.key_hash: fingerprint.request_hash,
                },
                "ai_field_confirmation_result_version": current_version + 1,
            },
            session=session,
        )
        if updated is None:
            # 同键竞争者可能已率先提交，CAS 输家只回读并验证完全相同的收据。
            replay = await novel_repo.get_novel_by_id(novel_id, session=session)
            replay_receipts = dict(replay.get("ai_field_confirmation_receipts", {}))
            if fingerprint.key_hash in replay_receipts:
                if replay_receipts[fingerprint.key_hash] != fingerprint.request_hash:
                    raise IdempotencyConflictError(
                        "同一 Idempotency-Key 已用于不同的小说字段确认请求"
                    )
                return replay
            raise VersionConflictError("小说在字段候选确认期间已发生变化")
        return updated

    @staticmethod
    async def get_novel(novel_id: str) -> dict[str, Any]:
        """读取一个活动小说。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            活动小说 BSON 文档。
        """
        return await novel_repo.get_novel_by_id(novel_id)

    @staticmethod
    async def list_novels(*, deleted: bool = False) -> list[dict[str, Any]]:
        """读取书架或回收站小说列表。

        Args:
            deleted: True 时读取回收站，否则读取活动书架。

        Returns:
            按仓储稳定顺序排列的小说文档列表。
        """
        if deleted:
            return await novel_repo.get_deleted_novels()
        return await novel_repo.get_all_novels()

    @staticmethod
    async def _get_versioned_novel(
        novel_id: str,
        expected_version: int,
        *,
        deleted: bool,
        session: Any = None,
    ) -> dict[str, Any]:
        """读取指定生命周期状态并验证小说版本与物理删除声明。"""
        expected = validate_expected_version(expected_version)
        novel = await novel_repo.get_novel_by_id(
            novel_id,
            include_deleted=True,
            session=session,
        )
        if bool(novel.get("is_deleted")) is not deleted:
            raise NotFoundError(f"小说 {novel_id} 不存在于当前生命周期视图")
        if novel.get("hard_delete_claim"):
            raise VersionConflictError("小说正在执行物理删除，不能再修改生命周期")
        current = int(novel["version"])
        if current != expected:
            raise VersionConflictError(
                f"小说版本冲突：当前版本为 {current}，请求版本为 {expected}"
            )
        return novel

    @staticmethod
    async def update_novel(
        novel_id: str,
        request: Any,
        *,
        session: Any = None,
    ) -> dict[str, Any]:
        """按 expected_version 更新活动小说人工字段。

        Args:
            novel_id: 小说 ObjectId 字符串。
            request: 含 expected_version 的严格更新请求。
            session: 调用方事务；提供时不另开事务。

        Returns:
            版本恰好递增一次的写后小说。
        """
        payload = _plain_dict(request, exclude_unset=True)
        expected_version = payload.pop("expected_version")
        payload.pop("request_type", None)
        fields = _prepare_novel_fields(payload)
        novel = await NovelService._get_versioned_novel(novel_id, expected_version, deleted=False, session=session)
        updated = await _update_novel_fields(novel, fields, session=session)
        if updated is None:
            raise VersionConflictError("小说在更新期间已发生变化")
        return updated

    @staticmethod
    async def update_status(
        novel_id: str,
        status: str,
        expected_version: int,
        *,
        session: Any = None,
    ) -> dict[str, Any]:
        """按 expected_version 更新活动小说状态。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            status: draft、ongoing、completed 或 archived。
            expected_version: 调用方基于的小说版本。
            session: 调用方事务；提供时不另开事务。

        Returns:
            版本递增一次的写后小说。
        """
        if status not in {"draft", "ongoing", "completed", "archived"}:
            raise ValueError(f"小说状态不合法: {status}")
        await NovelService._get_versioned_novel(novel_id, expected_version, deleted=False, session=session)
        updated = await novel_repo.update_versioned_novel(
            novel_id, expected_version, {"status": status}, is_deleted=False, session=session,
        )
        if updated is None:
            raise VersionConflictError("小说在状态更新期间已发生变化")
        return updated

    @staticmethod
    async def soft_delete_novel(
        novel_id: str,
        expected_version: int,
        *,
        session: Any = None,
    ) -> dict[str, Any]:
        """按 expected_version 将活动小说移入回收站。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            expected_version: 调用方基于的小说版本。
            session: 调用方事务；提供时不另开事务。

        Returns:
            标记为已删除且版本递增一次的小说。
        """
        await NovelService._get_versioned_novel(novel_id, expected_version, deleted=False, session=session)
        updated = await novel_repo.update_versioned_novel(
            novel_id, expected_version, {"is_deleted": True, "deleted_at": get_utc_now()},
            is_deleted=False, session=session,
        )
        if updated is None:
            raise VersionConflictError("小说在软删除期间已发生变化")
        return updated

    @staticmethod
    async def restore_novel(
        novel_id: str,
        expected_version: int,
        *,
        session: Any = None,
    ) -> dict[str, Any]:
        """按 expected_version 从回收站恢复小说。

        Args:
            novel_id: 回收站小说 ObjectId 字符串。
            expected_version: 调用方基于的小说版本。
            session: 调用方事务；提供时不另开事务。

        Returns:
            恢复为活动状态且版本递增一次的小说。
        """
        await NovelService._get_versioned_novel(novel_id, expected_version, deleted=True, session=session)
        updated = await novel_repo.update_versioned_novel(
            novel_id, expected_version, {"is_deleted": False, "deleted_at": None},
            is_deleted=True, session=session,
        )
        if updated is None:
            raise VersionConflictError("小说在恢复期间已发生变化")
        return updated

    @staticmethod
    async def set_cover(
        novel_id: str,
        expected_version: int,
        asset: EncodedCoverAsset,
    ) -> dict[str, Any]:
        """原子落盘封面并以小说 CAS 绑定资产 URL。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            expected_version: 调用方基于的小说版本。
            asset: 已安全重编码的封面内容。

        Returns:
            更新封面后的严格版本小说文档。
        """
        async with cover_asset_write_lock():
            snapshot = await NovelService._get_versioned_novel(
                novel_id,
                expected_version,
                deleted=False,
            )
            created_file = await asyncio.to_thread(store_cover_asset, asset)
            try:
                updated = await novel_repo.update_versioned_novel(
                    novel_id,
                    expected_version,
                    {"cover_image": asset.url},
                    is_deleted=False,
                )
                if updated is None:
                    raise VersionConflictError("小说在封面更新期间已发生变化")
            except Exception:
                if created_file and await novel_repo.count_cover_references(asset.url) == 0:
                    try:
                        await asyncio.to_thread(remove_cover_asset, asset.url)
                    except OSError:
                        logger.exception("小说 %s 的 CAS 失败封面补偿清理失败", novel_id)
                raise

            old_url = snapshot.get("cover_image")
            if (
                isinstance(old_url, str)
                and old_url != asset.url
                and await novel_repo.count_cover_references(old_url) == 0
            ):
                try:
                    await asyncio.to_thread(remove_cover_asset, old_url)
                except OSError:
                    logger.exception("小说 %s 的旧封面清理失败", novel_id)
            return updated

    @staticmethod
    async def clear_cover(
        novel_id: str,
        expected_version: int,
    ) -> dict[str, Any]:
        """以小说 CAS 解除封面引用并按共享引用计数清理文件。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            expected_version: 调用方基于的小说版本。

        Returns:
            封面字段为空且版本递增一次的小说。
        """
        async with cover_asset_write_lock():
            snapshot = await NovelService._get_versioned_novel(
                novel_id,
                expected_version,
                deleted=False,
            )
            updated = await novel_repo.update_versioned_novel(
                novel_id,
                expected_version,
                {"cover_image": None},
                is_deleted=False,
            )
            if updated is None:
                raise VersionConflictError("小说在封面清除期间已发生变化")
            old_url = snapshot.get("cover_image")
            if (
                isinstance(old_url, str)
                and await novel_repo.count_cover_references(old_url) == 0
            ):
                try:
                    await asyncio.to_thread(remove_cover_asset, old_url)
                except OSError:
                    logger.exception("小说 %s 的已解除封面清理失败", novel_id)
            return updated

    @staticmethod
    async def increment_stats(
        novel_id: str,
        stats_deltas: Mapping[str, int],
        *,
        session: Any = None,
    ) -> None:
        """由卷等直接消费者更新小说派生统计并递增公开版本。

        Args:
            novel_id: 活动小说 ObjectId 字符串。
            stats_deltas: 允许的卷数、章数或字数增量。
            session: 可选 MongoDB 会话。

        Returns:
            无。
        """
        changed = await novel_repo.increment_novel_stats(
            novel_id,
            stats_deltas,
            session=session,
        )
        if not changed:
            raise NotFoundError(f"小说 {novel_id} 不存在或统计增量为空")

    @staticmethod
    async def hard_delete_novel(
        novel_id: str,
        expected_version: int,
        *, expected_revision_count: int | None = None,
        expected_chapter_record_counts: ChapterRecordDeleteCountsV1 | Mapping[str, int] | None = None,
    ) -> dict[str, int]:
        """物理删除回收站小说及当前真实消费者并清理安全封面。

        Args:
            novel_id: 回收站小说 ObjectId 字符串。
            expected_version: 调用方确认的回收站版本。
            expected_revision_count: 作者明确确认要永久删除的章节历史数量。
            expected_chapter_record_counts: 作者明确批准的全部章后记录、回执和报告头数量。

        Returns:
            仅包含真实集合、小说文档与封面文件的精确删除计数。
        """
        expected = validate_expected_version(expected_version)
        approved_records = (ChapterRecordDeleteCountsV1.model_validate(expected_chapter_record_counts).model_dump()
                            if expected_chapter_record_counts is not None else None)
        claim_token = hashlib.sha256(
            f"{novel_id}:{expected}:hard-delete".encode("ascii")
        ).hexdigest()

        async def delete(session: Any) -> tuple[dict[str, int], str | None]:
            snapshot = await novel_repo.get_novel_by_id(
                novel_id,
                include_deleted=True,
                session=session,
            )
            if snapshot.get("is_deleted") is not True:
                raise NotFoundError(f"小说 {novel_id} 不在回收站")
            current = int(snapshot["version"])
            if current != expected:
                raise VersionConflictError(
                    f"小说版本冲突：当前版本为 {current}，请求版本为 {expected}"
                )
            obj_id = to_object_id(novel_id)
            novel_query = {"novel_id": obj_id}
            # 先处理伏笔再取得删除占用；已回收伏笔仍然保护原文和计划位置。
            foreshadowings = await BaseRepository("foreshadowings").collection.count_documents(novel_query, session=session)
            if foreshadowings:
                raise DomainApiError("NOVEL_FORESHADOWING_DELETE_BLOCKED", "作品仍有伏笔，请在已删作品的伏笔列表逐条回收，再到伏笔回收站永久删除", status_code=409, details={"foreshadowings": foreshadowings})
            # 无事务时不能先留删除声明再拒绝；回收站内不可改章，后续声明 CAS 防止并发恢复。
            revisions = BaseRepository("chapter_revisions").collection
            if snapshot.get("hard_delete_claim") == claim_token and "hard_delete_history_count" in snapshot:
                # 非事务删除可能已删部分历史；重入核对首次批准数量，不改为剩余数量。
                if expected_revision_count != snapshot["hard_delete_history_count"]:
                    raise VersionConflictError("请使用原确认的历史数量继续永久删除")
            else:
                has_history = await revisions.find_one(novel_query, {"_id": 1}, session=session)
                if has_history and expected_revision_count is None:
                    raise DomainApiError("NOVEL_HISTORY_DELETE_BLOCKED", "作品有章节历史版本，请先查看删除影响并明确确认", status_code=409)
                count = await revisions.count_documents(novel_query, session=session) if has_history else 0
                if expected_revision_count is not None and expected_revision_count != count:
                    raise VersionConflictError("作品章节历史数量已变化，请重新查看删除影响")
            record_counts = await count_novel_chapter_records(obj_id, session=session)
            if any(record_counts.values()):
                if session is None or not session.in_transaction:
                    raise TransactionNotSupportedError("作品含章后记录，必须启用数据库事务才能永久删除")
                if approved_records is None:
                    raise DomainApiError("NOVEL_CHAPTER_RECORD_DELETE_BLOCKED", "作品有章后确认记录，请先查看删除影响并明确确认全部数量", status_code=409, details={"chapter_records": record_counts})
            if approved_records is not None and approved_records != record_counts:
                raise VersionConflictError("作品章后记录数量已变化，请重新查看删除影响")
            # 新记录和作废都会改内部护栏；claim 绑定本次读取，封住非事务判空后的竞争。
            claimed = await novel_repo.claim_hard_delete(
                novel_id,
                expected,
                claim_token,
                session=session,
                expected_writing_guard_revision=snapshot.get("writing_guard_revision"),
                **({"expected_revision_count": expected_revision_count} if expected_revision_count is not None else {}),
            )
            if claimed is None:
                raise VersionConflictError("小说物理删除声明发生并发冲突")

            volumes_repo = BaseRepository("volumes")
            volumes = await volumes_repo.find_many(
                novel_query,
                include_deleted=True,
                session=session,
            )
            volume_ids = [item["_id"] for item in volumes]
            arc_query: dict[str, Any] = {"novel_id": obj_id}
            if volume_ids:
                arc_query = {
                    "$or": [
                        {"novel_id": obj_id},
                        {"volume_id": {"$in": volume_ids}},
                    ]
                }

            stats = {
                f"{name}_deleted": await BaseRepository(name).hard_delete_many(novel_query, session=session)
                for name in RECORD_COLLECTIONS
            }
            stats.update({
                "foreshadowing_creation_receipts_deleted": await BaseRepository("foreshadowing_creation_receipts").hard_delete_many(novel_query, session=session),
                "chapter_revisions_deleted": await BaseRepository("chapter_revisions").hard_delete_many(novel_query, session=session),
                "chapters_deleted": await BaseRepository("chapters").hard_delete_many(
                    novel_query, session=session,
                ),
                "scenes_deleted": await BaseRepository("scenes").hard_delete_many(
                    novel_query, session=session,
                ),
                "writing_confirmation_receipts_deleted": await BaseRepository(
                    "writing_confirmation_receipts"
                ).hard_delete_many(novel_query, session=session),
                "arcs_deleted": await BaseRepository("arcs").hard_delete_many(
                    arc_query,
                    session=session,
                ),
                "character_volume_states_deleted": await BaseRepository(
                    "character_volume_states"
                ).hard_delete_many(novel_query, session=session),
                "character_volume_state_initialization_receipts_deleted": await BaseRepository(
                    "character_volume_state_initialization_receipts"
                ).hard_delete_many(novel_query, session=session),
                "faction_volume_states_deleted": await BaseRepository(
                    "faction_volume_states"
                ).hard_delete_many(novel_query, session=session),
                "faction_volume_state_initialization_receipts_deleted": await BaseRepository(
                    "faction_volume_state_initialization_receipts"
                ).hard_delete_many(novel_query, session=session),
                "character_relations_deleted": await BaseRepository(
                    "character_relations"
                ).hard_delete_many(novel_query, session=session),
                "character_creation_batch_receipts_deleted": await BaseRepository(
                    "character_creation_batch_receipts"
                ).hard_delete_many(novel_query, session=session),
                "faction_creation_batch_receipts_deleted": await BaseRepository(
                    "faction_creation_batch_receipts"
                ).hard_delete_many(novel_query, session=session),
                "character_faction_bindings_deleted": await BaseRepository(
                    "character_faction_bindings"
                ).hard_delete_many(novel_query, session=session),
                "faction_relations_deleted": await BaseRepository(
                    "faction_relations"
                ).hard_delete_many(novel_query, session=session),
                "factions_deleted": await BaseRepository("factions").hard_delete_many(
                    novel_query,
                    session=session,
                ),
                "characters_deleted": await BaseRepository(
                    "characters"
                ).hard_delete_many(novel_query, session=session),
                "world_rules_deleted": await BaseRepository(
                    "world_rules"
                ).hard_delete_many(novel_query, session=session),
                "world_rule_core_confirmation_receipts_deleted": await BaseRepository(
                    "world_rule_core_confirmation_receipts"
                ).hard_delete_many(novel_query, session=session),
                "locations_deleted": await BaseRepository(
                    "locations"
                ).hard_delete_many(novel_query, session=session),
                "items_deleted": await BaseRepository("items").hard_delete_many(
                    novel_query,
                    session=session,
                ),
                "item_generation_confirmation_receipts_deleted": await BaseRepository(
                    "item_generation_confirmation_receipts"
                ).hard_delete_many(novel_query, session=session),
                "location_generation_confirmation_receipts_deleted": await BaseRepository(
                    "location_generation_confirmation_receipts"
                ).hard_delete_many(novel_query, session=session),
                "volume_command_receipts_deleted": await BaseRepository(
                    "volume_command_receipts"
                ).hard_delete_many(novel_query, session=session),
                "volumes_deleted": await volumes_repo.hard_delete_many(
                    novel_query,
                    session=session,
                ),
                "id_sequences_deleted": await BaseRepository(
                    "id_sequences"
                ).hard_delete_many(novel_query, session=session),
            })
            deleted = await novel_repo.delete_claimed_novel(
                novel_id,
                expected,
                claim_token,
                session=session,
            )
            if not deleted:
                raise VersionConflictError("小说物理删除结束时声明已失效")
            stats["novel_deleted"] = 1
            cover_url = claimed.get("cover_image")
            return stats, cover_url if isinstance(cover_url, str) else None

        stats, cover_url = await run_mongo_write_unit(delete, "hard_delete_novel")
        stats["cover_asset_deleted"] = 0
        if cover_url:
            async with cover_asset_write_lock():
                if await novel_repo.count_cover_references(cover_url) == 0:
                    try:
                        stats["cover_asset_deleted"] = int(
                            await asyncio.to_thread(remove_cover_asset, cover_url)
                        )
                    except OSError:
                        # 正式数据已完成物理删除；文件系统故障保留为可审计孤儿文件，不能伪装回滚。
                        logger.exception("小说 %s 的无引用封面文件清理失败", novel_id)
        return stats


__all__ = [
    "AI_CREATE_SCHEMA_ID",
    "AI_CREATE_SCHEMA_VERSION",
    "AI_CREATE_FINAL_STEP",
    "AI_CREATE_WORKFLOW",
    "NOVEL_EDITABLE_FIELDS",
    "NovelService",
]
