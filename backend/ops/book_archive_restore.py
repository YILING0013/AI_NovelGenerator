"""只向操作者独占的全新副本集目标恢复；数据库单事务，封面单独发布。"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re

from bson import BSON
from bson.codec_options import CodecOptions, DatetimeConversion
from bson.raw_bson import RawBSONDocument
from pymongo import ReadPreference
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from backend.ops.book_archive import load_verified_archive
from backend.ops.book_archive_contract import (
    ArchiveValidationError, FORESHADOWING_COLLECTIONS, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION,
    FACTION_BATCH_COLLECTIONS as COLLECTIONS, COMBINED_FORMAT_VERSION,
)
from backend.ops.book_archive_cover import ArchiveCoverError, publish_cover, verify_cover
from backend.ops.book_archive_indexes import BOOK_INDEXES, V4_BOOK_INDEXES, V7_BOOK_INDEXES, V8_BOOK_INDEXES, V10_BOOK_INDEXES, V11_BOOK_INDEXES, V12_BOOK_INDEXES, V13_BOOK_INDEXES, index_catalog_digest
from backend.ops.book_archive_warnings import driver_warning_guard


RESTORE_COLLECTION = "_book_archive_restore"
RECEIPT_ID = "restore-empty"
RESTORE_PROFILE_VERSION = 1
RAW_CODEC = CodecOptions(document_class=RawBSONDocument, tz_aware=True,
                         datetime_conversion=DatetimeConversion.DATETIME_AUTO)


class ArchiveRestoreError(ArchiveValidationError):
    """保存脱敏错误及数据库、封面、核验三个独立状态。"""

    def __init__(self, code: str, location: str, message: str) -> None:
        """记录明确错误，不保留可能带连接信息的驱动原文。

        Args:
            code: 固定错误码。
            location: 参数名或操作步骤。
            message: 可直接告诉操作者的说明。
        """
        super().__init__(location, message)
        self.code = code
        self.report: dict = {}


async def _catalog(database) -> dict:
    """完整读取事务外目录；结果只表示读取时的观察。

    Args:
        database: 显式目标数据库。
    Returns:
        按集合名保存的完整目录。
    """
    cursor = await database.list_collections(
        nameOnly=False, authorizedCollections=False,
        cursor={"batchSize": 100}, maxTimeMS=10_000,
    )
    async with cursor:
        return {entry["name"]: entry async for entry in cursor}


async def _read_receipt(database) -> bytes | None:
    """从 primary 用 majority 读取固定回执，不据此推断不存在的事务已回滚。

    Args:
        database: 显式目标数据库。
    Returns:
        固定回执的原始 BSON，或当下尚未读到回执的 None。
    """
    collection = database.with_options(
        codec_options=RAW_CODEC, read_concern=ReadConcern("majority"),
        read_preference=ReadPreference.PRIMARY,
    )[RESTORE_COLLECTION]
    document = await collection.find_one({"_id": RECEIPT_ID}, max_time_ms=10_000)
    return None if document is None else document.raw


async def _verify_restored(database, raw_documents, receipt_bytes, cover_content, cover_entry, covers_dir, *, index_catalog=None) -> None:
    """只读核对全部原始文档、目录、索引和封面；不修复已有内容。

    Args:
        database: 显式目标数据库。
        raw_documents: 本次已验证包对应的原始 BSON 列表。
        receipt_bytes: 本次操作预期的完整回执。
        cover_content: 已验证封面字节或 None。
        cover_entry: 已验证封面描述或 None。
        covers_dir: 操作者独占的显式封面目录。
        index_catalog: 已确认回执对应的原索引目录；省略时使用当前目录。
    Returns:
        无；不完全一致时抛出错误。
    """
    index_catalog = BOOK_INDEXES if index_catalog is None else index_catalog
    catalog = await _catalog(database)
    if set(catalog) != {*index_catalog, RESTORE_COLLECTION} or any(
        entry["type"] != "collection" or entry.get("options", {}) for entry in catalog.values()
    ):
        raise ArchiveRestoreError("RESTORED_DATA_CHANGED", "verify_catalog", "目标集合、视图或集合选项与恢复结果不同")
    raw_database = database.with_options(
        codec_options=RAW_CODEC, read_concern=ReadConcern("majority"),
        read_preference=ReadPreference.PRIMARY,
    )
    for name in (*index_catalog, RESTORE_COLLECTION):
        expected = [receipt_bytes] if name == RESTORE_COLLECTION else raw_documents[name]
        cursor = raw_database[name].find({}, batch_size=100, max_time_ms=60_000)
        async with cursor:
            actual = sorted([bytes(document.raw) async for document in cursor])
        if actual != sorted(expected):
            raise ArchiveRestoreError("RESTORED_DATA_CHANGED", "verify_documents", "目标原始文档与已验证备份不同")
        wanted = {"_id_": {"name": "_id_", "key": [("_id", 1)], "unique": False}}
        if name != RESTORE_COLLECTION:
            for model in index_catalog[name]:
                definition = dict(model.document)
                definition["key"] = list(definition["key"].items())
                definition.setdefault("unique", False)
                wanted[definition["name"]] = definition
        indexes = await database[name].list_indexes()
        actual_indexes = {}
        async with indexes:
            async for index in indexes:
                definition = dict(index)
                # 服务端补充索引格式版本；其余选项必须与本版明确目录一致。
                definition.pop("v", None)
                definition["key"] = list(definition["key"].items())
                definition.setdefault("unique", False)
                actual_indexes[definition["name"]] = definition
        if actual_indexes != wanted:
            raise ArchiveRestoreError("RESTORED_DATA_CHANGED", "verify_indexes", "目标索引名称、顺序或选项与本版恢复目录不同")
    verify_cover(cover_content, cover_entry, covers_dir=covers_dir)


async def restore_empty(
    archive_path: str | Path, *, target_uri_env: str, target_database: str,
    target_covers_dir: str | Path, confirm_isolated_target: str,
) -> dict:
    """向独占全新目标执行一次完整数据库事务，或只读确认相同恢复已完成。

    Args:
        archive_path: 单书 ZIP，验证后只使用持有的内存内容。
        target_uri_env: 唯一允许读取的 URI 环境变量名。
        target_database: 显式目标库名，不使用应用配置或 URI 默认库。
        target_covers_dir: 操作者独占的现有普通封面目录。
        confirm_isolated_target: 必须精确等于目标库名，确认没有应用、维护或其他写入者。
    Returns:
        分别说明数据库提交、封面发布和完整核验的结果。
    Raises:
        ArchiveRestoreError: 失败或取消时保留已知状态；不输出连接信息。
    """
    report = {
        "status": "restore_failed", "target_database": None,
        "database_state": "not_committed", "cover_state": "not_published",
        "verification_state": "not_run", "namespace_count": None,
        "exclusive_access": "operator_required_not_verified",
        "cross_resource_atomicity": "not_available", "archive_validation": {"status": "not_run"},
    }
    client = session = None
    error = None
    location = "input"
    commit_entered = False
    observed_fresh = False
    # 异步 DNS、会话、提交、关闭都可能产生含 URI 选项的警告，保护持续到关闭结束。
    with driver_warning_guard():
        try:
            if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target_uri_env)
                    or not os.environ.get(target_uri_env, "").strip()):
                raise ArchiveRestoreError("INVALID_INPUT", "target_uri_env", "必须指定有值的连接环境变量名")
            if (not target_database or len(target_database.encode("utf-8")) > 63
                    or re.search(r'[/\\. "$*<>:|?\s\x00]', target_database)
                    or target_database.lower() in {"admin", "local", "config"}):
                raise ArchiveRestoreError("INVALID_INPUT", "target_database", "必须指定有效目标库名，不能使用系统库")
            if confirm_isolated_target != target_database:
                raise ArchiveRestoreError("INVALID_INPUT", "confirm_isolated_target", "确认值必须精确等于目标库名，并由操作者保证独占目标库和封面目录")
            report["target_database"] = target_database
            location = "archive"
            payload = load_verified_archive(archive_path)
            report["archive_validation"] = payload.report
            report["payload_identity"] = payload.payload_identity
            # Mongo 写入必将顶层 _id 放首位；不允许“恢复成功”却悄悄改变包中顺序。
            if any(next(iter(doc)) != "_id" for rows in payload.documents.values() for doc in rows):
                raise ArchiveRestoreError("UNSUPPORTED_DOCUMENT_ORDER", "archive", "MongoDB 会移动顶层 _id；本版只接受 _id 已在首位的文档，不改写包内字段顺序")
            # 两条独立历史格式按原目录恢复；不为 v11 补建人物批次集合。
            restore_indexes = {FACTION_FACT_FORMAT_VERSION: V11_BOOK_INDEXES,
                               CHARACTER_BATCH_FORMAT_VERSION: V12_BOOK_INDEXES,
                               COMBINED_FORMAT_VERSION: V13_BOOK_INDEXES}.get(payload.report["format_version"],
                                   V13_BOOK_INDEXES if payload.report["format_version"] < 14 else BOOK_INDEXES)
            # 原恢复回执比较完整 BSON；集合字段顺序沿用归档白名单，不能改成索引字典顺序。
            raw_documents = {name: [BSON.encode(doc) for doc in payload.documents.get(name, [])]
                             for name in COLLECTIONS if name in restore_indexes}
            cover_entry = next((entry for entry in payload.report["checked_files"]
                                if entry["path"].startswith("static/covers/")), None)
            cover_content = None if cover_entry is None else payload.cover_bytes[cover_entry["path"]]
            if cover_entry is None:
                report["cover_state"] = "not_needed"
            # verify_cover 的无封面调用仍验证显式目录；有封面时发布函数负责不存在的目标。
            from backend.ops.book_archive_cover import validate_covers_directory

            validate_covers_directory(target_covers_dir)
            receipt = {
                "_id": RECEIPT_ID, "profile_version": RESTORE_PROFILE_VERSION,
                "payload_identity": payload.payload_identity,
                "novel_id": payload.report["novel_id"], "source_revision": payload.report["source_revision"],
                "collections": {name: {"count": len(raw_documents[name]), "raw_document_digests": sorted(
                    hashlib.sha256(raw).hexdigest() for raw in raw_documents[name]
                )} for name in raw_documents},
                "index_catalog_digest": index_catalog_digest(restore_indexes),
                "cover": cover_entry,
            }
            receipt_bytes = BSON.encode(receipt)
            from pymongo import AsyncMongoClient

            location = "connect"
            client = AsyncMongoClient(
                os.environ[target_uri_env], read_preference=ReadPreference.PRIMARY,
                retryReads=False, retryWrites=False, directConnection=False,
                serverSelectionTimeoutMS=10_000, connectTimeoutMS=10_000, socketTimeoutMS=60_000,
            )
            hello = await client.admin.command("hello")
            if (hello.get("maxWireVersion", 0) < 13 or hello.get("logicalSessionTimeoutMinutes") is None
                    or not hello.get("setName") or hello.get("msg") == "isdbgrid"
                    or hello.get("isWritablePrimary") is not True):
                raise ArchiveRestoreError("UNSUPPORTED_TARGET", "target", "只支持 MongoDB 5+ 且支持会话和事务内建集合、索引的副本集")
            database = client.get_database(target_database, read_preference=ReadPreference.PRIMARY)
            location = "catalog"
            catalog = await _catalog(database)
            report["namespace_count"] = len(catalog)
            if catalog:
                observed = await _read_receipt(database) if RESTORE_COLLECTION in catalog else None
                # 旧恢复回执的集合清单和索引摘要一起保留；只读核验，不补写新集合。
                candidates = [(receipt_bytes, restore_indexes)]
                for version, old_indexes in ((10, V10_BOOK_INDEXES), (8, V8_BOOK_INDEXES), (7, V7_BOOK_INDEXES)):
                    if payload.report["format_version"] <= version:
                        old_receipt = {**receipt, "collections": {name: entry for name, entry in receipt["collections"].items() if name in old_indexes},
                                       "index_catalog_digest": index_catalog_digest(old_indexes)}
                        candidates.append((BSON.encode(old_receipt), old_indexes))
                if payload.report["format_version"] <= 4:
                    old_receipt = {**receipt, "collections": {
                        name: receipt["collections"][name] for name in FORESHADOWING_COLLECTIONS
                    }, "index_catalog_digest": index_catalog_digest(V4_BOOK_INDEXES)}
                    candidates.append((BSON.encode(old_receipt), V4_BOOK_INDEXES))
                verified_receipt, verified_indexes = next((candidate for candidate in candidates if candidate[0] == observed), candidates[0])
                if observed != verified_receipt:
                    raise ArchiveRestoreError("TARGET_NOT_FRESH", location, "目标非全新，或恢复回执与本次包和版本不同；不会修复或覆盖")
                report["database_state"] = "committed"
                report["verification_state"] = "failed"
                await _verify_restored(database, raw_documents, verified_receipt, cover_content, cover_entry, target_covers_dir, index_catalog=verified_indexes)
                report["verification_state"] = "passed"
                report["cover_state"] = "not_needed" if cover_entry is None else "reused"
                report["status"] = "already_restored"
            else:
                observed_fresh = True
                location = "cover_publish"
                report["cover_state"] = publish_cover(cover_content, cover_entry, covers_dir=target_covers_dir)
                # 目录观察不是数据库锁。操作者必须保证没有任何外部写入者。
                location = "catalog"
                if await _catalog(database):
                    raise ArchiveRestoreError("TARGET_NOT_FRESH", location, "发布封面后目标目录发生变化，停止数据库写入")
                session = client.start_session(causal_consistency=False)
                await session.start_transaction(
                    read_concern=ReadConcern("local"), write_concern=WriteConcern("majority"),
                    read_preference=ReadPreference.PRIMARY, max_commit_time_ms=60_000,
                )
                location = "transaction_ddl"
                await database.create_collection(RESTORE_COLLECTION, session=session, check_exists=False)
                # 固定回执尽早参加同一事务，只串行化遵守本协议的恢复；不是外部客户端的锁。
                await database[RESTORE_COLLECTION].insert_one(RawBSONDocument(receipt_bytes), session=session)
                for name in raw_documents:
                    await database.create_collection(name, session=session, check_exists=False)
                    await database[name].create_indexes(restore_indexes[name], session=session)
                location = "transaction_insert"
                for name in raw_documents:
                    if await database[name].find_one({}, session=session) is not None:
                        raise ArchiveRestoreError("TARGET_NOT_FRESH", location, "事务内目标集合已有文档，停止恢复")
                    if raw_documents[name]:
                        await database[name].insert_many(
                            [RawBSONDocument(raw) for raw in raw_documents[name]], ordered=True, session=session,
                        )
                location = "commit"
                # 必须先记录阶段；进入 await 后的取消或丢响应不能当作回滚。
                commit_entered = True
                report["database_state"] = "commit_unknown"
                for attempt in range(3):
                    try:
                        await session.commit_transaction()
                        report["database_state"] = "committed"
                        break
                    except (PyMongoError, TimeoutError) as exc:
                        retryable = isinstance(exc, (ConnectionFailure, TimeoutError)) or (
                            isinstance(exc, PyMongoError) and exc.has_error_label("UnknownTransactionCommitResult")
                        )
                        if not retryable or attempt == 2:
                            raise
                location = "verification"
                report["verification_state"] = "failed"
                await _verify_restored(database, raw_documents, receipt_bytes, cover_content, cover_entry, target_covers_dir, index_catalog=restore_indexes)
                report["verification_state"] = "passed"
                report["status"] = "restored"
        except (Exception, asyncio.CancelledError) as exc:
            allow_reconciled_success = isinstance(exc, (PyMongoError, TimeoutError)) or (
                isinstance(exc, ArchiveRestoreError) and exc.code == "TARGET_NOT_FRESH"
            )
            if isinstance(exc, ArchiveCoverError):
                if location == "cover_publish":
                    report["cover_state"] = exc.cover_state
                error = ArchiveRestoreError(exc.code, exc.location, exc.message)
            elif isinstance(exc, ArchiveRestoreError):
                error = exc
            elif isinstance(exc, ArchiveValidationError):
                error = ArchiveRestoreError("INVALID_ARCHIVE", exc.location, exc.message)
            elif isinstance(exc, asyncio.CancelledError):
                error = ArchiveRestoreError("CANCELLED", location, "恢复被取消，请根据提交状态只读核对结果")
            elif isinstance(exc, Warning):
                error = ArchiveRestoreError("DRIVER_WARNING", location, "目标连接选项或驱动操作产生警告，已停止并保留已知状态")
            elif location == "transaction_ddl" and isinstance(exc, OperationFailure) and exc.code == 263:
                error = ArchiveRestoreError("UNSUPPORTED_TARGET", location, "目标不支持事务内创建集合或索引，不能执行本版恢复")
            else:
                code = "COMMIT_UNKNOWN" if report["database_state"] == "commit_unknown" else "RESTORE_FAILED"
                error = ArchiveRestoreError(code, location, "目标操作失败；不会降级普通写入、拆分提交或重跑写入流程")
            if session is not None and not commit_entered:
                try:
                    await session.abort_transaction()
                except (Exception, asyncio.CancelledError):
                    report.setdefault("cleanup_errors", []).append("transaction_abort")
            # 未知提交只确认 majority 回执。无回执可能仍在提交，不能宣布未提交。
            # 事务前并发冲突也仅重新观察，绝不重跑写入体。
            if (client is not None and observed_fresh and location != "cover_publish"
                    and report["database_state"] != "committed"):
                try:
                    observed = await _read_receipt(database)
                    if not commit_entered and error.code != "CANCELLED":
                        for _ in range(4):
                            if observed is not None:
                                break
                            await asyncio.sleep(0.1)
                            observed = await _read_receipt(database)
                    if observed == receipt_bytes:
                        report["database_state"] = "committed"
                        report["verification_state"] = "failed"
                        await _verify_restored(database, raw_documents, receipt_bytes, cover_content, cover_entry, target_covers_dir, index_catalog=restore_indexes)
                        report["verification_state"] = "passed"
                        if allow_reconciled_success:
                            error = None
                            report["status"] = "already_restored"
                    elif session is not None and not commit_entered:
                        report["namespace_count"] = len(await _catalog(database))
                except ArchiveValidationError as verification_error:
                    error = ArchiveRestoreError(
                        getattr(verification_error, "code", "VERIFICATION_FAILED"),
                        verification_error.location, verification_error.message,
                    )
                except (Exception, asyncio.CancelledError):
                    # 保留原失败及未知状态，不以读取失败推断事务结果。
                    if report["database_state"] == "committed" and error.code != "CANCELLED":
                        error = ArchiveRestoreError("VERIFICATION_FAILED", "verification", "已确认数据库提交，但完整只读核验失败")
        finally:
            # 未知提交时不请求 abort；关闭客户端释放本地资源，重启后凭回执只读识别。
            for stage, resource in (("session_close", session), ("client_close", client)):
                if resource is None or (stage == "session_close" and report["database_state"] == "commit_unknown"):
                    continue
                try:
                    if stage == "session_close":
                        await resource.end_session()
                    else:
                        await resource.close()
                except (Exception, asyncio.CancelledError):
                    report.setdefault("cleanup_errors", []).append(stage)
                    if error is None:
                        error = ArchiveRestoreError("CLOSE_FAILED", stage, "资源关闭失败；已知提交和封面状态保持不变")
    if error is not None:
        report["status"] = "restore_failed"
        error.report = report
        raise error from None
    return report
