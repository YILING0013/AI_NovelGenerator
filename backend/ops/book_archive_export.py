"""从显式 MongoDB 源只读导出单书；不加载应用配置或数据库写入入口。"""

from __future__ import annotations

from datetime import timezone
from decimal import DecimalException
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from bson import BSON, ObjectId
from bson.codec_options import CodecOptions, DatetimeConversion
from bson.errors import BSONError
from bson.raw_bson import RawBSONDocument

from backend.ops import book_archive as archive
from backend.ops.book_archive_contract import ArchiveValidationError, FACTION_BATCH_COLLECTIONS as COLLECTIONS, validate_documents
from backend.ops.book_archive_warnings import driver_warning_guard


BATCH_SIZE = 100
RAW_CODEC = CodecOptions(
    document_class=RawBSONDocument, tz_aware=True, tzinfo=timezone.utc,
    datetime_conversion=DatetimeConversion.DATETIME_AUTO,
)
DOCUMENT_CODEC = RAW_CODEC.with_options(document_class=dict)


class ArchiveExportError(ArchiveValidationError):
    """记录完整文件是否已经发布，避免把清理失败说成没有输出。"""

    def __init__(self, location: str, message: str, *, published: bool = False) -> None:
        """保存失败位置和发布状态。

        Args:
            location: 失败的参数、包成员或输出步骤。
            message: 不含连接信息的说明。
            published: 是否已创建完整目标文件。
        """
        super().__init__(location, message)
        self.published = published


async def export_book(
    *, source_uri_env: str, source_database: str, novel_id: str,
    source_covers_dir: str | Path, source_revision: str, output: str | Path,
) -> dict:
    """在同一个只读快照会话内导出白名单原始文档，验证后发布新 ZIP。

    Args:
        source_uri_env: 唯一允许读取的源 MongoDB URI 环境变量名。
        source_database: 明确指定的源数据库，不使用 URI 默认库。
        novel_id: 24 位小写十六进制小说 ObjectId。
        source_covers_dir: 明确指定的封面目录，只读取快照文档引用的文件。
        source_revision: 调用方提供的完整源码提交号。
        output: 尚不存在的目标 ZIP；父目录必须已存在。
    Returns:
        离线校验结果、输出路径和已发布状态；不包含源连接信息。
    Raises:
        ArchiveValidationError: 参数、快照、源文档或封面不符合要求。
        ArchiveExportError: 文件操作失败；published 表明有效目标是否已发布。
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", source_uri_env):
        raise ArchiveValidationError("source_uri_env", "必须指定有效的环境变量名")
    uri = os.environ.get(source_uri_env)
    if not uri or not uri.strip():
        raise ArchiveValidationError("source_uri_env", "指定的源连接环境变量没有值")
    if (not source_database or len(source_database.encode("utf-8")) > 63
            or re.search(r'[/\\. "$*<>:|?\x00]', source_database)):
        raise ArchiveValidationError("source_database", "必须指定有效的源数据库名")
    if not re.fullmatch(r"[0-9a-f]{24}", novel_id):
        raise ArchiveValidationError("novel_id", "小说 ID 必须是 24 位小写 ObjectId")
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ArchiveValidationError("source_revision", "源码版本必须是完整 Git 提交号")
    if not str(source_covers_dir).strip():
        raise ArchiveValidationError("source_covers_dir", "必须明确指定封面目录")
    try:
        covers = Path(source_covers_dir).absolute()
        cover_dir_stat = covers.lstat()
        if (not stat.S_ISDIR(cover_dir_stat.st_mode) or covers.is_symlink()
                or getattr(cover_dir_stat, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ArchiveValidationError("source_covers_dir", "封面目录必须是现有普通目录，不能是链接")
        destination = Path(output).absolute()
        if os.path.lexists(destination):
            raise ArchiveValidationError("output", "目标已存在，不能覆盖")
        destination = destination.parent.resolve(strict=True) / destination.name
        if not destination.parent.is_dir():
            raise ArchiveValidationError("output", "目标父目录必须已存在")
    except (OSError, ValueError) as exc:
        if isinstance(exc, ArchiveValidationError):
            raise
        raise ArchiveValidationError("paths", "源封面目录或目标路径无效、缺失或不可访问") from None

    # 参数和本地路径检查通过后才加载驱动，help、verify 不会走到这里。
    from pymongo import AsyncMongoClient, ReadPreference
    from pymongo.errors import PyMongoError

    staging = None
    published = False
    location = "source"
    try:
        descriptor, staging_name = tempfile.mkstemp(prefix=".book-export-", suffix=".zip", dir=destination.parent)
        staging = Path(staging_name)
        # SRV TXT 可能延后解析；直到关闭客户端都要把原始选项警告转为失败。
        with os.fdopen(descriptor, "w+b") as stream, driver_warning_guard():
            client = AsyncMongoClient(
                uri, read_preference=ReadPreference.PRIMARY, retryReads=False, retryWrites=False,
                directConnection=False,
                serverSelectionTimeoutMS=10_000, connectTimeoutMS=10_000, socketTimeoutMS=60_000,
            )
            try:
                hello = await client.admin.command("hello")
                if (hello.get("maxWireVersion", 0) < 13 or hello.get("logicalSessionTimeoutMinutes") is None
                        or not (hello.get("setName") or hello.get("msg") == "isdbgrid")):
                    raise ArchiveValidationError("source", "导出需要 MongoDB 5+、会话和副本集或分片集群")
                database = client.get_database(
                    source_database, codec_options=RAW_CODEC, read_preference=ReadPreference.PRIMARY,
                )
                documents = {name: [] for name in COLLECTIONS}
                entries = {}
                record_count = total_bytes = json_nodes = 0
                book_id = ObjectId(novel_id)
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as bundle:
                    async with client.start_session(snapshot=True, causal_consistency=False) as session:
                        for name in COLLECTIONS:
                            path = f"collections/{name}.jsonl"
                            location = path
                            digest = hashlib.sha256()
                            collection_bytes = 0
                            query = {"_id" if name == "novels" else "novel_id": book_id}
                            cursor = database[name].find(query, session=session).sort("_id", 1).batch_size(BATCH_SIZE)
                            with bundle.open(path, "w") as member:
                                async with cursor:
                                    async for raw_document in cursor:
                                        location = f"{path}:{len(documents[name]) + 1}"
                                        record_count += 1
                                        if record_count > archive.MAX_RECORDS:
                                            raise ArchiveValidationError(location, "文档总数超过限制")
                                        # 先约束单条原始数据，再解码；不能对 RawBSONDocument 编码来检查保真，它会直接透传。
                                        if len(raw_document.raw) > archive.MAX_LINE_BYTES:
                                            raise ArchiveValidationError(location, "单条原始 BSON 超过大小限制")
                                        raw = bytes(raw_document.raw)
                                        document = BSON(raw).decode(codec_options=DOCUMENT_CODEC)
                                        if BSON.encode(document, codec_options=DOCUMENT_CODEC) != raw:
                                            raise ArchiveValidationError(location, "原始 BSON 包含无法无损保留的字段或类型")
                                        line = archive.encode_document(document)
                                        _, nodes = archive._parse_json(line, location)
                                        json_nodes += nodes
                                        collection_bytes += len(line)
                                        total_bytes += len(line)
                                        if (collection_bytes > archive.MAX_COLLECTION_BYTES
                                                or total_bytes > archive.MAX_TOTAL_BYTES
                                                or json_nodes > archive.MAX_JSON_NODES):
                                            raise ArchiveValidationError(location, "集合、总字节或 JSON 字段数量超过限制")
                                        # 所有累计限额均在保存本条前检查；关系检查只保留限额内的原始文档。
                                        documents[name].append(document)
                                        member.write(line)
                                        digest.update(line)
                                        if stream.tell() > archive.MAX_ARCHIVE_BYTES:
                                            raise ArchiveValidationError(location, "备份包超过大小限制")
                            entries[name] = {"path": path, "count": len(documents[name]),
                                             "size_bytes": collection_bytes, "sha256": digest.hexdigest()}
                    summary = validate_documents(documents, book_id, format_version=archive.FACTION_VOLUME_START_FORMAT_VERSION)
                    assets = []
                    cover = documents["novels"][0].get("cover_image")
                    if cover not in (None, ""):
                        location = "collections/novels.jsonl:1:cover_image"
                        match = archive._COVER_PATH.fullmatch(cover[1:]) if isinstance(cover, str) and cover.startswith("/") else None
                        if match is None:
                            raise ArchiveValidationError(location, "封面必须引用带 SHA256 的受支持文件名")
                        cover_path = covers / Path(cover).name
                        before = cover_path.lstat()
                        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                                or getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                            raise ArchiveValidationError(location, "封面必须是普通文件，不能是链接")
                        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                        with os.fdopen(os.open(cover_path, flags), "rb") as cover_stream:
                            opened = os.fstat(cover_stream.fileno())
                            current = cover_path.lstat()
                            if (not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened)
                                    or not os.path.samestat(opened, current) or stat.S_ISLNK(current.st_mode)
                                    or getattr(current, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                                raise ArchiveValidationError(location, "封面在打开时被替换，导出已停止")
                            if opened.st_size > archive.MAX_COVER_BYTES:
                                raise ArchiveValidationError(location, "封面超过大小限制")
                            content = cover_stream.read(archive.MAX_COVER_BYTES + 1)
                        if len(content) > archive.MAX_COVER_BYTES or hashlib.sha256(content).hexdigest() != match[1]:
                            raise ArchiveValidationError(location, "封面大小或 SHA256 与小说引用不符")
                        total_bytes += len(content)
                        if total_bytes > archive.MAX_TOTAL_BYTES:
                            raise ArchiveValidationError(location, "包内总字节超过限制")
                        bundle.writestr(cover[1:], content)
                        assets.append({"path": cover[1:], "size_bytes": len(content), "sha256": match[1]})
                    location = "manifest.json"
                    manifest = {
                        "format": archive.FORMAT, "format_version": archive.FACTION_VOLUME_START_FORMAT_VERSION,
                        "source_revision": source_revision, "novel_id": novel_id, "complete": True,
                        "encoding": archive.ENCODING, "collections": entries, "assets": assets,
                        "validation_summary": summary, "scope": archive.FACTION_VOLUME_START_EXPORT_SCOPE,
                        "export_profile": archive.EXPORT_PROFILE,
                    }
                    content = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    _, nodes = archive._parse_json(content, location)
                    if (len(content) > archive.MAX_MANIFEST_BYTES or total_bytes + len(content) > archive.MAX_TOTAL_BYTES
                            or json_nodes + nodes > archive.MAX_JSON_NODES):
                        raise ArchiveValidationError(location, "清单、总字节或 JSON 字段数量超过限制")
                    bundle.writestr(location, content)
            finally:
                await client.close()
            location = "staging"
            if stream.tell() > archive.MAX_ARCHIVE_BYTES:
                raise ArchiveValidationError(location, "备份包超过大小限制")
            stream.flush()
            os.fsync(stream.fileno())
        result = archive.verify_archive(staging)
        location = "publish"
        # 硬链接一次性发布完整文件；目标在此刻出现也会失败，绝不退回覆盖 rename 或复制。
        os.link(staging, destination)
        published = True
        if os.name != "nt":
            directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        return {**result, "status": "exported", "output": str(destination), "published": True}
    except PyMongoError:
        raise ArchiveExportError(location, "源数据库连接或快照读取失败；未改用普通读取", published=published) from None
    except Warning:
        raise ArchiveExportError(location, "源连接选项无效或不受支持", published=published) from None
    except ArchiveValidationError:
        raise
    except (BSONError, DecimalException, ValueError, TypeError, OverflowError, RecursionError, SystemError):
        raise ArchiveExportError(location, "源 BSON 类型不支持或无法无损编码", published=published) from None
    except (OSError, zipfile.LargeZipFile):
        message = "完整目标已发布，但后续文件同步失败" if published else "读取、写入或发布失败；未发布目标"
        raise ArchiveExportError(location, message, published=published) from None
    finally:
        if staging is not None:
            try:
                staging.unlink()
            except OSError:
                message = "完整目标已发布，但临时文件清理失败" if published else "导出未发布，临时文件清理失败"
                raise ArchiveExportError("staging_cleanup", message, published=published) from None
