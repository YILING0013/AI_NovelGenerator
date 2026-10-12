"""只读观察显式恢复目标；不写数据库、封面或检查回执。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

from backend.ops.book_archive import verify_archive
from backend.ops.book_archive_contract import ArchiveValidationError
from backend.ops.book_archive_warnings import driver_warning_guard


class ArchiveTargetError(ArchiveValidationError):
    """携带稳定错误码和截至失败时的只读检查结果。"""

    def __init__(self, code: str, location: str, message: str) -> None:
        """保存不含连接信息的失败原因。

        Args:
            code: 供程序判断的固定错误码。
            location: 出错参数或检查步骤。
            message: 可直接告诉操作人的说明。
        """
        super().__init__(location, message)
        self.code = code
        self.report: dict = {}


async def inspect_target(
    archive_path: str | Path, *, target_uri_env: str, target_database: str,
    target_covers_dir: str | Path,
) -> dict:
    """验证单书包，并观察目标库是否完全没有集合或视图。

    Args:
        archive_path: 只读验证的单书 ZIP 路径。
        target_uri_env: 唯一允许读取的目标 URI 环境变量名。
        target_database: 显式目标库名，不使用 URI 默认库或应用配置。
        target_covers_dir: 已有普通目录，只检查包内封面对应的文件名。
    Returns:
        包验证、完整目录计数、封面检查结果和未验证的恢复条件。
    Raises:
        ArchiveTargetError: 参数、包、封面或目标检查失败；不包含 URI。
    """
    report = {
        "status": "invalid", "target_database": None, "namespace_count": None,
        "archive_validation": {"status": "not_run"}, "covers": [],
        "database_restore": "not_run", "target_check": "read_only_observation",
        "exclusive_access": "operator_required_not_verified",
        "future_target_empty": "not_verified", "write_permissions": "not_verified",
        "transaction_execution": "not_verified",
    }
    try:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target_uri_env):
            raise ArchiveTargetError("INVALID_INPUT", "target_uri_env", "必须指定有效的环境变量名")
        uri = os.environ.get(target_uri_env)
        if not uri or not uri.strip():
            raise ArchiveTargetError("INVALID_INPUT", "target_uri_env", "指定的目标连接环境变量没有值")
        if (not target_database or len(target_database.encode("utf-8")) > 63
                or re.search(r'[/\\. "$*<>:|?\s\x00]', target_database)
                or target_database.lower() in {"admin", "local", "config"}):
            raise ArchiveTargetError("INVALID_INPUT", "target_database", "必须指定有效的目标库名，不能使用系统库")
        report["target_database"] = target_database
        if not str(target_covers_dir).strip():
            raise ArchiveTargetError("INVALID_INPUT", "target_covers_dir", "必须明确指定封面目录")
        try:
            covers = Path(target_covers_dir).absolute()
            directory = covers.lstat()
            if (not stat.S_ISDIR(directory.st_mode) or stat.S_ISLNK(directory.st_mode)
                    or getattr(directory, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ArchiveTargetError("INVALID_INPUT", "target_covers_dir", "封面目录必须是现有普通目录，不能是链接")
        except (OSError, ValueError):
            raise ArchiveTargetError("INVALID_INPUT", "target_covers_dir", "封面目录无效、缺失或不可访问") from None

        report["archive_validation"] = verify_archive(archive_path)
        # 只用验证器已核对过的文件描述，不重开 ZIP，也不扫描封面目录。
        for entry in report["archive_validation"]["checked_files"]:
            if not entry["path"].startswith("static/covers/"):
                continue
            observed = {**entry, "status": "conflict"}
            report["covers"].append(observed)
            path = covers / Path(entry["path"]).name
            try:
                try:
                    before = path.lstat()
                except FileNotFoundError:
                    observed["status"] = "absent"
                    continue
                if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                        or getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                        or before.st_size != entry["size_bytes"]):
                    raise ArchiveTargetError("COVER_CONFLICT", "target_cover", "目标封面不是大小相同的普通文件")
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                with os.fdopen(os.open(path, flags), "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    current = path.lstat()
                    if (not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened)
                            or not os.path.samestat(opened, current) or stat.S_ISLNK(current.st_mode)
                            or getattr(current, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                        raise ArchiveTargetError("COVER_CONFLICT", "target_cover", "目标封面在打开时被替换")
                    content = stream.read(entry["size_bytes"] + 1)
                if len(content) != entry["size_bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
                    raise ArchiveTargetError("COVER_CONFLICT", "target_cover", "目标封面大小或 SHA256 与包内文件不同")
                observed["status"] = "same"
            except OSError:
                raise ArchiveTargetError("COVER_CONFLICT", "target_cover", "无法完整读取目标封面") from None

        # 所有本地检查通过后才加载驱动；不用应用数据库或可能写索引的入口。
        from pymongo import AsyncMongoClient, ReadPreference
        from pymongo.errors import PyMongoError

        try:
            # SRV 选项可能在首次 await 时才解析，关闭阶段也不得泄露选项原文。
            with driver_warning_guard():
                client = AsyncMongoClient(
                    uri, read_preference=ReadPreference.PRIMARY, retryReads=False, retryWrites=False,
                    directConnection=False,
                    serverSelectionTimeoutMS=10_000, connectTimeoutMS=10_000, socketTimeoutMS=60_000,
                )
                try:
                    hello = await client.admin.command("hello")
                    if (hello.get("maxWireVersion", 0) < 13 or hello.get("logicalSessionTimeoutMinutes") is None
                            or not hello.get("setName") or hello.get("msg") == "isdbgrid"):
                        raise ArchiveTargetError("UNSUPPORTED_TARGET", "target", "首版恢复目标只支持 MongoDB 5+ 且支持会话的副本集")
                    database = client.get_database(target_database, read_preference=ReadPreference.PRIMARY)
                    # listCollections 不支持 snapshot 会话；这只是当下观察，不保证未来仍为空。
                    async with client.start_session(causal_consistency=False) as session:
                        cursor = await database.list_collections(
                            nameOnly=False, authorizedCollections=False, session=session,
                            cursor={"batchSize": 100}, maxTimeMS=10_000,
                        )
                        count = 0
                        async with cursor:
                            async for _ in cursor:
                                count += 1
                        report["namespace_count"] = count
                    if count:
                        raise ArchiveTargetError("TARGET_NOT_FRESH", "target", "目标库已有集合或视图，必须使用完全没有集合和视图的目标库")
                finally:
                    await client.close()
        except (PyMongoError, OSError, ValueError, Warning) as exc:
            if isinstance(exc, ArchiveTargetError):
                raise
            raise ArchiveTargetError("TARGET_INSPECTION_FAILED", "target", "目标连接、完整目录读取或客户端关闭失败") from None
        report["status"] = "target_empty_observed"
        return report
    except ArchiveValidationError as exc:
        if not isinstance(exc, ArchiveTargetError):
            report["archive_validation"] = {"status": "invalid", "error": {"location": exc.location, "message": exc.message}}
            exc = ArchiveTargetError("INVALID_ARCHIVE", exc.location, exc.message)
        report["status"] = ("conflict" if exc.code in {"TARGET_NOT_FRESH", "COVER_CONFLICT"}
                            else "invalid" if exc.code in {"INVALID_INPUT", "INVALID_ARCHIVE"} else "error")
        exc.report = report
        raise exc from None
