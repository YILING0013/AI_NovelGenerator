"""离线检查单书包；仅显式数据库子命令按需加载各自入口。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import struct
import zipfile
import zlib
from dataclasses import dataclass
from decimal import DecimalException
from pathlib import Path
from typing import BinaryIO

from bson import BSON, ObjectId
from bson.codec_options import DatetimeConversion
from bson.errors import BSONError
from bson.json_util import CANONICAL_JSON_OPTIONS, dumps, loads

from backend.ops.book_archive_contract import (
    COLLECTIONS,
    REVISION_COLLECTIONS,
    FORESHADOWING_COLLECTIONS,
    CHAPTER_RECORD_COLLECTIONS, CHARACTER_BATCH_COLLECTIONS, FACTION_BATCH_COLLECTIONS, CHARACTER_BATCH_FORMAT_VERSION,
    FACTION_FACT_FORMAT_VERSION, COMBINED_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSIONS,
    FACTION_VOLUME_START_FORMAT_VERSION,
    CORE_COLLECTIONS,
    ArchiveValidationError,
    validate_documents,
)


FORMAT = "private-ai-novel-book-archive"
FORMAT_VERSION = 1
EXPORT_FORMAT_VERSION = 2
REVISION_FORMAT_VERSION = 3
FORESHADOWING_FORMAT_VERSION = 4
CHAPTER_RECORD_FORMAT_VERSION = 5
ITEM_OWNER_FORMAT_VERSION = 6
CHARACTER_RELATION_STATE_FORMAT_VERSION = 7
CHARACTER_FACT_FORMAT_VERSION = 8
CHARACTER_RELATION_FACT_FORMAT_VERSION = 9
ITEM_FACT_FORMAT_VERSION = 10
ENCODING = "canonical_extended_jsonl_v2"
JSON_OPTIONS = CANONICAL_JSON_OPTIONS.with_options(
    tz_aware=True, datetime_conversion=DatetimeConversion.DATETIME_AUTO,
)
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_COLLECTION_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_LINE_BYTES = 8 * 1024 * 1024
MAX_COVER_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_JSON_NODES = 1_000_000
MAX_JSON_DEPTH = 64
# 单书最多一张封面；中央目录也要先限大小，避免仅打开 ZIP 就耗尽内存。
MAX_MEMBERS = len(FACTION_BATCH_COLLECTIONS) + 2
MAX_DIRECTORY_BYTES = 32 * 1024
ARCHIVE_SCOPE = {
    "documents": "raw_bson",
    "soft_deleted": "included",
    "historical_business_ids": "included",
    "successful_receipts": "included",
    "flow_definitions": "not_included",
    "assistant_runtime": "not_included",
    "derived_indexes_and_leases": "not_included",
    "managed_configuration_and_credentials": "not_included",
    "writing_history_basis_and_flow_snapshot": "not_persisted_in_source",
    "database_export": "not_run",
    "database_restore": "not_run",
    "snapshot_consistency": "not_verified",
    "target_database_safety": "not_verified",
}
EXPORT_SCOPE = {
    **ARCHIVE_SCOPE,
    "database_export": "snapshot_read_completed",
    "snapshot_consistency": "exporter_declared",
}
REVISION_EXPORT_SCOPE = {**EXPORT_SCOPE, "chapter_revisions": "included"}
FORESHADOWING_EXPORT_SCOPE = {**REVISION_EXPORT_SCOPE, "foreshadowings": "included", "foreshadowing_creation_receipts": "included"}
CHAPTER_RECORD_EXPORT_SCOPE = {**FORESHADOWING_EXPORT_SCOPE, "chapter_records": "included", "chapter_record_confirmation_receipts": "included"}
CHARACTER_FACT_EXPORT_SCOPE = {**CHAPTER_RECORD_EXPORT_SCOPE, "character_facts": "included"}
CHARACTER_RELATION_FACT_EXPORT_SCOPE = {**CHARACTER_FACT_EXPORT_SCOPE, "character_relation_facts": "included"}
ITEM_FACT_EXPORT_SCOPE = {**CHARACTER_RELATION_FACT_EXPORT_SCOPE, "item_facts": "included"}
FACTION_FACT_EXPORT_SCOPE = {**ITEM_FACT_EXPORT_SCOPE, "faction_facts": "included"}
CHARACTER_BATCH_EXPORT_SCOPE = {**ITEM_FACT_EXPORT_SCOPE, "character_creation_batch_receipts": "included"}
COMBINED_EXPORT_SCOPE = {**FACTION_FACT_EXPORT_SCOPE, "character_creation_batch_receipts": "included"}
FACTION_VOLUME_START_EXPORT_SCOPE = {**COMBINED_EXPORT_SCOPE, "faction_volume_start": "included", "faction_creation_batch_receipts": "included"}
EXPORT_PROFILE = {
    "database_read": "pymongo_snapshot_session",
    "read_preference": "primary",
    "cover_read": "hash_checked_not_snapshot",
    "attestation": "exporter_claim_not_independently_verified",
}
_HEX64 = re.compile(r"[0-9a-f]{64}")
_COVER_PATH = re.compile(r"static/covers/([0-9a-f]{64})\.(?:jpg|png|webp)")


@dataclass(frozen=True)
class VerifiedArchive:
    """保存本次已验证的原文档、封面字节和报告，恢复时不再打开源 ZIP。"""

    report: dict
    documents: dict[str, list[dict]]
    cover_bytes: dict[str, bytes]
    payload_identity: str


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """拒绝 JSON 重复键，避免前后两次解析读到不同字段。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 包含重复字段")
        result[key] = value
    return result


def _parse_json(content: bytes, location: str) -> tuple[object, int]:
    """严格读取 UTF-8 JSON，并限制嵌套与对象数量。"""
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
        stack = [(value, 0)]
        nodes = 0
        while stack:
            current, depth = stack.pop()
            nodes += 1
            if depth > MAX_JSON_DEPTH or nodes > MAX_JSON_NODES:
                raise ValueError("JSON 嵌套或字段数量超过限制")
            if isinstance(current, dict):
                # 本格式只允许 EJSON v2；旧二进制形状会进入 PyMongo 的宽松解析分支。
                if "$binary" in current and "$type" in current:
                    raise ValueError("不接受旧版 BSON 二进制编码")
                binary = current.get("$binary")
                if isinstance(binary, dict) and isinstance(binary.get("subType"), str) and binary["subType"].lower() == "ff":
                    # 当前 PyMongo C 编码器处理 ff 会抛 SystemError，不能改成别的子类型继续。
                    raise ValueError("当前 BSON 编码器不支持二进制子类型 ff")
                stack.extend((child, depth + 1) for child in current.values())
            elif isinstance(current, list):
                stack.extend((child, depth + 1) for child in current)
        # 普通 JSON 不允许 NaN、Infinity 或未配对的 Unicode 代理字符。
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value, nodes
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ArchiveValidationError(location, "UTF-8 JSON 无效、字段重复、编码不受支持或超过限制") from exc


def encode_document(document: dict) -> bytes:
    """把原始 BSON 文档编码为一行 UTF-8，保留 BSON 类型和正文空白。

    Args:
        document: 原始数据库文档，不经过 HTTP DTO 或创建、更新模型。
    Returns:
        以 LF 结尾的 Canonical Extended JSON；不写文件。
    """
    content = (dumps(document, json_options=JSON_OPTIONS, ensure_ascii=False,
                     separators=(",", ":")) + "\n").encode("utf-8")
    # BSON 日期只有毫秒精度；拒绝编码时改变原始 BSON 含义的输入。
    decoded = decode_document(content)
    if BSON.encode(document) != BSON.encode(decoded):
        raise ArchiveValidationError("document", "文档不能无损编码为 BSON JSON")
    return content


def decode_document(content: bytes, location: str = "document") -> dict:
    """读取一行可逆 BSON JSON，不修改字段或正文。

    Args:
        content: 一行 UTF-8 Canonical Extended JSON 字节。
        location: 出错时报告的文件和行号。
    Returns:
        保留 ObjectId、UTC 日期等 BSON 类型的文档。
    """
    if len(content) > MAX_LINE_BYTES:
        raise ArchiveValidationError(location, "单条文档超过大小限制")
    raw, _ = _parse_json(content, location)
    if not isinstance(raw, dict):
        raise ArchiveValidationError(location, "每行必须是一个文档")
    try:
        document = loads(content.decode("utf-8"), json_options=JSON_OPTIONS)
        if not isinstance(document, dict):
            raise ValueError("顶层不是文档")
        # BSON 的 Timestamp 等类型会接受布尔值；检查实际 BSON 往返，不能用 True == 1。
        restored = BSON(BSON.encode(document)).decode(codec_options=JSON_OPTIONS)
        canonical = json.loads(dumps(restored, json_options=JSON_OPTIONS))
        if json.dumps(raw, sort_keys=True) != json.dumps(canonical, sort_keys=True):
            raise ValueError("不是可逆的 Canonical Extended JSON")
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, BSONError, DecimalException) as exc:
        raise ArchiveValidationError(location, "BSON 编码无效或不符合 Canonical Extended JSON v2") from exc
    return document


def _check_deflate(source: BinaryIO, member: zipfile.ZipInfo, data_offset: int) -> None:
    """检查完整压缩流，避免 zipfile 按声明长度截断后遗漏隐藏内容。

    Args:
        source: 只读 ZIP 文件。
        member: 已检查大小的成员信息。
        data_offset: 压缩数据的起始位置。
    """
    source.seek(data_offset)
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    remaining = member.compress_size
    size = 0
    checksum = 0
    while remaining:
        chunk = source.read(min(64 * 1024, remaining))
        if not chunk:
            raise ArchiveValidationError(member.filename, "压缩内容不完整")
        remaining -= len(chunk)
        while chunk:
            decoded = decoder.decompress(chunk, min(64 * 1024, member.file_size - size + 1))
            size += len(decoded)
            checksum = zlib.crc32(decoded, checksum)
            if size > member.file_size or decoder.unused_data or (decoder.eof and remaining):
                raise ArchiveValidationError(member.filename, "压缩流包含未声明的内容")
            chunk = decoder.unconsumed_tail
    if not decoder.eof or size != member.file_size or checksum != member.CRC:
        raise ArchiveValidationError(member.filename, "压缩流不完整或长度、校验值不符")


def load_verified_archive(path: str | Path) -> VerifiedArchive:
    """只读验证 ZIP 的全部内容，并保留本次实际验证过的文档和封面。

    Args:
        path: 已存在的备份包路径。
    Returns:
        验证报告、保留 BSON 类型和字段顺序的文档、封面字节和内容标识。
    Raises:
        ArchiveValidationError: 包不完整、格式不合法或关联不一致。
    """
    location = "archive"
    try:
        with Path(path).open("rb") as source:
            source.seek(0, 2)
            archive_size = source.tell()
            if archive_size > MAX_ARCHIVE_BYTES or archive_size < 22:
                raise ArchiveValidationError(location, "备份包为空、不完整或超过大小限制")
            # v1 不接受 ZIP64、分卷、注释或尾随内容；先读固定尾部，再交给 zipfile。
            source.seek(-22, 2)
            end = source.read(22)
            signature, disk, directory_disk, disk_count, count, size, offset, comment = struct.unpack("<4s4H2LH", end)
            if (signature != b"PK\x05\x06" or disk or directory_disk or comment
                    or disk_count != count or not 1 <= count <= MAX_MEMBERS
                    or size > MAX_DIRECTORY_BYTES or offset + size != archive_size - 22):
                raise ArchiveValidationError(location, "ZIP 目录不完整、超限或使用了不支持的格式")
            source.seek(0)
            with zipfile.ZipFile(source) as bundle:
                members = bundle.infolist()
                if len(members) != count or len({member.filename for member in members}) != count:
                    raise ArchiveValidationError(location, "ZIP 包含重复成员或目录数量不符")
                files = {}
                data_offsets = {}
                total_size = 0
                next_offset = 0
                for member in sorted(members, key=lambda value: value.header_offset):
                    location = member.filename
                    if member.volume != 0:
                        raise ArchiveValidationError(location, "不支持跨磁盘的 ZIP 成员")
                    mode = member.external_attr >> 16
                    if (member.orig_filename != member.filename or member.is_dir()
                            or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                            or member.flag_bits & ~0x800 or member.extra or member.comment
                            or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                        raise ArchiveValidationError(location, "只接受无附加元数据、无数据描述符的未加密普通文件")
                    # 中央目录可能故意漏掉本地成员；检查连续边界，禁止藏在目录之外的文件。
                    if member.header_offset != next_offset:
                        raise ArchiveValidationError(location, "ZIP 含未列入目录的数据或重叠文件")
                    source.seek(next_offset)
                    header = source.read(30)
                    if len(header) != 30:
                        raise ArchiveValidationError(location, "ZIP 本地文件头不完整")
                    local = struct.unpack("<4s5H3L2H", header)
                    if (local[0] != b"PK\x03\x04" or local[2] != member.flag_bits
                            or local[3] != member.compress_type or local[6] != member.CRC
                            or local[7] != member.compress_size or local[8] != member.file_size
                            or local[10] != 0):
                        raise ArchiveValidationError(location, "ZIP 本地文件头与目录不符")
                    if member.compress_type == zipfile.ZIP_STORED and member.compress_size != member.file_size:
                        raise ArchiveValidationError(location, "未压缩文件的字节长度不符")
                    data_offsets[location] = next_offset + 30 + local[9]
                    next_offset += 30 + local[9] + member.compress_size
                    if member.filename == "manifest.json":
                        limit = MAX_MANIFEST_BYTES
                    elif member.filename in {f"collections/{name}.jsonl" for name in FACTION_BATCH_COLLECTIONS}:
                        limit = MAX_COLLECTION_BYTES
                    elif _COVER_PATH.fullmatch(member.filename):
                        limit = MAX_COVER_BYTES
                    else:
                        raise ArchiveValidationError(location, "未知文件或不安全路径")
                    total_size += member.file_size
                    if member.file_size > limit or total_size > MAX_TOTAL_BYTES:
                        raise ArchiveValidationError(location, "解压后大小超过限制")
                    files[member.filename] = member
                if next_offset != offset:
                    raise ArchiveValidationError("archive", "ZIP 包含目录外的数据")
                location = "manifest.json"
                if location not in files:
                    raise ArchiveValidationError(location, "缺少清单")
                for member in members:
                    location = member.filename
                    if member.compress_type == zipfile.ZIP_DEFLATED:
                        _check_deflate(source, member, data_offsets[location])
                location = "manifest.json"
                manifest_bytes = bundle.read(files[location])
                manifest, json_nodes = _parse_json(manifest_bytes, location)
                keys = {"format", "format_version", "source_revision", "novel_id", "complete",
                        "encoding", "collections", "assets", "validation_summary", "scope"}
                if not isinstance(manifest, dict):
                    raise ArchiveValidationError(location, "清单字段不符合固定版本")
                if (manifest.get("format") != FORMAT or type(manifest.get("format_version")) is not int
                        or manifest["format_version"] not in (FORMAT_VERSION, EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION)):
                    raise ArchiveValidationError(location, "未知备份格式版本；仅支持 1–14")
                version = manifest["format_version"]
                if version in (EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION):
                    keys.add("export_profile")
                if set(manifest) != keys:
                    raise ArchiveValidationError(location, "清单字段不符合固定版本")
                if manifest["complete"] is not True or manifest["encoding"] != ENCODING:
                    raise ArchiveValidationError(location, "备份未完成或文档编码不支持")
                if not isinstance(manifest["source_revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_revision"]):
                    raise ArchiveValidationError(location, "源码版本必须是完整 Git 提交号")
                if not isinstance(manifest["novel_id"], str) or not re.fullmatch(r"[0-9a-f]{24}", manifest["novel_id"]):
                    raise ArchiveValidationError(location, "小说 ID 格式无效")
                scope = ARCHIVE_SCOPE if version == FORMAT_VERSION else EXPORT_SCOPE
                if version == REVISION_FORMAT_VERSION:
                    scope = REVISION_EXPORT_SCOPE
                if version == FORESHADOWING_FORMAT_VERSION:
                    scope = FORESHADOWING_EXPORT_SCOPE
                if version in (CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION):
                    scope = CHAPTER_RECORD_EXPORT_SCOPE
                if version == CHARACTER_FACT_FORMAT_VERSION:
                    scope = CHARACTER_FACT_EXPORT_SCOPE
                if version == CHARACTER_RELATION_FACT_FORMAT_VERSION:
                    scope = CHARACTER_RELATION_FACT_EXPORT_SCOPE
                if version == ITEM_FACT_FORMAT_VERSION:
                    scope = ITEM_FACT_EXPORT_SCOPE
                if version == FACTION_FACT_FORMAT_VERSION:
                    scope = FACTION_FACT_EXPORT_SCOPE
                if version == CHARACTER_BATCH_FORMAT_VERSION:
                    scope = CHARACTER_BATCH_EXPORT_SCOPE
                if version == COMBINED_FORMAT_VERSION:
                    scope = COMBINED_EXPORT_SCOPE
                if version == FACTION_VOLUME_START_FORMAT_VERSION:
                    scope = FACTION_VOLUME_START_EXPORT_SCOPE
                if manifest["scope"] != scope:
                    raise ArchiveValidationError(location, "清单必须如实声明本版本的验证范围与缺口")
                if version in (EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION) and manifest["export_profile"] != EXPORT_PROFILE:
                    raise ArchiveValidationError(location, "导出方式声明不符合本版本要求")
                collections = manifest["collections"]
                names = REVISION_COLLECTIONS if version == REVISION_FORMAT_VERSION else COLLECTIONS
                if version == FORESHADOWING_FORMAT_VERSION:
                    names = FORESHADOWING_COLLECTIONS
                if version in (CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION):
                    names = CHAPTER_RECORD_COLLECTIONS
                if version in CHARACTER_BATCH_FORMAT_VERSIONS:
                    names = CHARACTER_BATCH_COLLECTIONS
                if version == FACTION_VOLUME_START_FORMAT_VERSION:
                    names = FACTION_BATCH_COLLECTIONS
                if not isinstance(collections, dict) or set(collections) != set(names):
                    raise ArchiveValidationError(location, "集合必须与完整白名单一致，包括空集合")
                assets = manifest["assets"]
                if not isinstance(assets, list) or len(assets) > 1:
                    raise ArchiveValidationError(location, "单书只能包含实际引用的封面")
                expected = {"manifest.json"}
                descriptors = []
                for name in names:
                    entry = collections[name]
                    if (not isinstance(entry, dict) or set(entry) != {"path", "count", "size_bytes", "sha256"}
                            or entry["path"] != f"collections/{name}.jsonl"
                            or type(entry["count"]) is not int or not 0 <= entry["count"] <= MAX_RECORDS):
                        raise ArchiveValidationError(location, f"集合 {name} 的清单无效")
                    descriptors.append(entry)
                for entry in assets:
                    if (not isinstance(entry, dict) or set(entry) != {"path", "size_bytes", "sha256"}
                            or not isinstance(entry["path"], str) or not _COVER_PATH.fullmatch(entry["path"])):
                        raise ArchiveValidationError(location, "封面清单无效")
                    descriptors.append(entry)
                for entry in descriptors:
                    if (type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0
                            or not isinstance(entry["sha256"], str) or not _HEX64.fullmatch(entry["sha256"])):
                        raise ArchiveValidationError(location, "文件长度或 SHA256 格式无效")
                    expected.add(entry["path"])
                if set(files) != expected:
                    raise ArchiveValidationError(location, "存在未声明文件或缺少清单中的文件")
                checked_files = [{"path": "manifest.json", "size_bytes": len(manifest_bytes),
                                  "sha256": hashlib.sha256(manifest_bytes).hexdigest()}]
                documents = {name: [] for name in names}
                cover_bytes = {}
                record_count = 0
                for entry in descriptors:
                    location = entry["path"]
                    member = files[location]
                    if entry["size_bytes"] != member.file_size:
                        raise ArchiveValidationError(location, "文件长度与清单不符")
                    digest = hashlib.sha256()
                    actual_size = 0
                    with bundle.open(member) as stream:
                        if location.startswith("collections/"):
                            name = location[len("collections/"):-len(".jsonl")]
                            while line := stream.readline(MAX_LINE_BYTES + 1):
                                line_number = len(documents[name]) + 1
                                line_location = f"{location}:{line_number}"
                                if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                                    raise ArchiveValidationError(line_location, "文档过大或末尾缺少 LF，备份可能未完成")
                                digest.update(line)
                                actual_size += len(line)
                                record_count += 1
                                if record_count > MAX_RECORDS:
                                    raise ArchiveValidationError(line_location, "文档总数超过限制")
                                _, nodes = _parse_json(line, line_location)
                                json_nodes += nodes
                                if json_nodes > MAX_JSON_NODES:
                                    raise ArchiveValidationError(line_location, "包内 JSON 字段总数超过限制")
                                documents[name].append(decode_document(line, line_location))
                            if len(documents[name]) != entry["count"]:
                                raise ArchiveValidationError(location, "文档数量与清单不符")
                        else:
                            cover_content = bytearray()
                            while chunk := stream.read(64 * 1024):
                                digest.update(chunk)
                                actual_size += len(chunk)
                                cover_content.extend(chunk)
                    if actual_size != entry["size_bytes"] or digest.hexdigest() != entry["sha256"]:
                        raise ArchiveValidationError(location, "文件字节 SHA256 或长度与清单不符")
                    if location.startswith("static/") and _COVER_PATH.fullmatch(location)[1] != digest.hexdigest():
                        raise ArchiveValidationError(location, "封面路径哈希与内容不一致")
                    if location.startswith("static/"):
                        cover_bytes[location] = bytes(cover_content)
                    checked_files.append({key: entry[key] for key in ("path", "size_bytes", "sha256")})
                summary = validate_documents(documents, ObjectId(manifest["novel_id"]), format_version=version)
                if json.dumps(summary, sort_keys=True) != json.dumps(manifest["validation_summary"], sort_keys=True):
                    raise ArchiveValidationError("manifest.json:validation_summary", "业务 ID 和父链检查摘要与实际数据不符")
                cover = documents["novels"][0].get("cover_image")
                cover_paths = {entry["path"] for entry in assets}
                if cover in (None, ""):
                    if cover_paths:
                        raise ArchiveValidationError("manifest.json:assets", "存在没有被小说引用的封面")
                elif not isinstance(cover, str) or not cover.startswith("/") or {cover[1:]} != cover_paths:
                    raise ArchiveValidationError("collections/novels.jsonl:1:cover_image", "封面引用与包内文件不一致")
                report = {
                    "status": "valid", "format_version": version,
                    "source_revision": manifest["source_revision"], "novel_id": manifest["novel_id"],
                    "collections": list(names),
                    "counts": {name: len(rows) for name, rows in documents.items()},
                    "checked_files": checked_files, "validation_summary": summary,
                    "scope": dict(scope),
                    **({"export_profile": dict(EXPORT_PROFILE)} if version in (EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION) else {}),
                }
                # 清单本身的实际字节也参与标识，不能只相信包中声明的哈希。
                payload_identity = hashlib.sha256(json.dumps(
                    checked_files, sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")).hexdigest()
                return VerifiedArchive(report, documents, cover_bytes, payload_identity)
    except (OSError, UnicodeError, zipfile.BadZipFile, EOFError, zlib.error, NotImplementedError) as exc:
        raise ArchiveValidationError(location, "无法读取文件，或 ZIP 已损坏、不完整") from exc


def verify_archive(path: str | Path) -> dict:
    """只读验证 ZIP 中的完整单书包，不连接数据库或提取文件到磁盘。

    Args:
        path: 已存在的备份包路径。
    Returns:
        格式版本、集合数量、文件哈希、层级与引用检查摘要及验证范围。
    Raises:
        ArchiveValidationError: 包不完整、格式不合法或关联不一致。
    """
    return load_verified_archive(path).report


def main(argv: list[str] | None = None) -> int:
    """运行显式选择的归档命令，通过返回 0，失败返回 1。

    Args:
        argv: 命令行参数；省略时使用进程参数。
    Returns:
        退出码；结果或定位错误以 JSON 输出到标准输出。
    """
    parser = argparse.ArgumentParser(description="单书备份包导出、离线验证、目标检查与显式隔离恢复")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="只读检查，不连接数据库")
    verify.add_argument("archive")
    export = commands.add_parser("export", help="从显式源数据库只读导出单书")
    export.add_argument("--source-uri-env", required=True)
    export.add_argument("--source-database", required=True)
    export.add_argument("--novel-id", required=True)
    export.add_argument("--source-covers-dir", required=True)
    export.add_argument("--source-revision", required=True)
    export.add_argument("--output", required=True)
    dry_run = commands.add_parser("dry-run", help="验证包并只读观察显式目标，不执行恢复")
    dry_run.add_argument("archive")
    dry_run.add_argument("--target-uri-env", required=True)
    dry_run.add_argument("--target-database", required=True)
    dry_run.add_argument("--target-covers-dir", required=True)
    restore = commands.add_parser(
        "restore-empty", help="将已验证的单书包恢复到独占的全新隔离目标",
        description="操作人必须独占隔离目标库和封面目录，确保没有应用、维护程序或其他写入者。"
                    "本命令不能阻止任意外部客户端写入，不提供数据库级安全锁。",
    )
    restore.add_argument("archive")
    restore.add_argument("--target-uri-env", required=True)
    restore.add_argument("--target-database", required=True)
    restore.add_argument("--target-covers-dir", required=True)
    restore.add_argument("--confirm-isolated-target", required=True, help="必须精确等于目标库名")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_archive(args.archive)
        elif args.command == "export":
            import asyncio

            from backend.ops.book_archive_export import export_book

            result = asyncio.run(export_book(
                source_uri_env=args.source_uri_env, source_database=args.source_database,
                novel_id=args.novel_id, source_covers_dir=args.source_covers_dir,
                source_revision=args.source_revision, output=args.output,
            ))
        elif args.command == "dry-run":
            import asyncio

            from backend.ops.book_archive_target import inspect_target

            result = asyncio.run(inspect_target(
                args.archive, target_uri_env=args.target_uri_env,
                target_database=args.target_database, target_covers_dir=args.target_covers_dir,
            ))
        else:
            import asyncio

            from backend.ops.book_archive_restore import restore_empty

            result = asyncio.run(restore_empty(
                args.archive, target_uri_env=args.target_uri_env,
                target_database=args.target_database, target_covers_dir=args.target_covers_dir,
                confirm_isolated_target=args.confirm_isolated_target,
            ))
    except ArchiveValidationError as exc:
        if args.command in {"dry-run", "restore-empty"}:
            print(json.dumps({**exc.report, "error": {"code": exc.code, "location": exc.location,
                                                    "message": exc.message}}, ensure_ascii=True))
            return 1
        print(json.dumps({"status": "invalid" if args.command == "verify" else "export_failed",
                          "error": {"location": exc.location, "message": exc.message},
                          **({"published": getattr(exc, "published", False)} if args.command == "export"
                             else {"scope": ARCHIVE_SCOPE})},
                         ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
