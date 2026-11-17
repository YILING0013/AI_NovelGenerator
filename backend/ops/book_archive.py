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
            raise ValueError("JSON chứa trường trùng lặp")
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
                raise ValueError("Độ sâu lồng nhau hoặc số trường của JSON vượt quá giới hạn")
            if isinstance(current, dict):
                # 本格式只允许 EJSON v2；旧二进制形状会进入 PyMongo 的宽松解析分支。
                if "$binary" in current and "$type" in current:
                    raise ValueError("Không chấp nhận mã nhị phân BSON kiểu cũ")
                binary = current.get("$binary")
                if isinstance(binary, dict) and isinstance(binary.get("subType"), str) and binary["subType"].lower() == "ff":
                    # 当前 PyMongo C 编码器处理 ff 会抛 SystemError，不能改成别的子类型继续。
                    raise ValueError("Bộ mã hóa BSON hiện tại không hỗ trợ subtype nhị phân ff")
                stack.extend((child, depth + 1) for child in current.values())
            elif isinstance(current, list):
                stack.extend((child, depth + 1) for child in current)
        # 普通 JSON 不允许 NaN、Infinity 或未配对的 Unicode 代理字符。
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value, nodes
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ArchiveValidationError(location, "UTF-8 JSON không hợp lệ, trường trùng lặp, mã hóa không được hỗ trợ hoặc vượt quá giới hạn") from exc


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
        raise ArchiveValidationError("document", "Tài liệu không thể mã hóa thành BSON JSON mà không bị mất dữ liệu")
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
        raise ArchiveValidationError(location, "Một tài liệu đơn lẻ vượt quá giới hạn kích thước")
    raw, _ = _parse_json(content, location)
    if not isinstance(raw, dict):
        raise ArchiveValidationError(location, "Mỗi dòng phải là một tài liệu")
    try:
        document = loads(content.decode("utf-8"), json_options=JSON_OPTIONS)
        if not isinstance(document, dict):
            raise ValueError("Cấp cao nhất không phải là một tài liệu")
        # BSON 的 Timestamp 等类型会接受布尔值；检查实际 BSON 往返，不能用 True == 1。
        restored = BSON(BSON.encode(document)).decode(codec_options=JSON_OPTIONS)
        canonical = json.loads(dumps(restored, json_options=JSON_OPTIONS))
        if json.dumps(raw, sort_keys=True) != json.dumps(canonical, sort_keys=True):
            raise ValueError("Không phải Canonical Extended JSON có thể đảo ngược")
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, BSONError, DecimalException) as exc:
        raise ArchiveValidationError(location, "Mã hóa BSON không hợp lệ hoặc không theo Canonical Extended JSON v2") from exc
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
            raise ArchiveValidationError(member.filename, "Nội dung nén không hoàn chỉnh")
        remaining -= len(chunk)
        while chunk:
            decoded = decoder.decompress(chunk, min(64 * 1024, member.file_size - size + 1))
            size += len(decoded)
            checksum = zlib.crc32(decoded, checksum)
            if size > member.file_size or decoder.unused_data or (decoder.eof and remaining):
                raise ArchiveValidationError(member.filename, "Luồng nén chứa nội dung không được khai báo")
            chunk = decoder.unconsumed_tail
    if not decoder.eof or size != member.file_size or checksum != member.CRC:
        raise ArchiveValidationError(member.filename, "Luồng nén không hoàn chỉnh hoặc độ dài, giá trị kiểm tra không khớp")


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
                raise ArchiveValidationError(location, "Gói sao lưu trống, không hoàn chỉnh hoặc vượt giới hạn kích thước")
            # v1 不接受 ZIP64、分卷、注释或尾随内容；先读固定尾部，再交给 zipfile。
            source.seek(-22, 2)
            end = source.read(22)
            signature, disk, directory_disk, disk_count, count, size, offset, comment = struct.unpack("<4s4H2LH", end)
            if (signature != b"PK\x05\x06" or disk or directory_disk or comment
                    or disk_count != count or not 1 <= count <= MAX_MEMBERS
                    or size > MAX_DIRECTORY_BYTES or offset + size != archive_size - 22):
                raise ArchiveValidationError(location, "Danh mục ZIP không hoàn chỉnh, vượt giới hạn hoặc dùng định dạng không được hỗ trợ")
            source.seek(0)
            with zipfile.ZipFile(source) as bundle:
                members = bundle.infolist()
                if len(members) != count or len({member.filename for member in members}) != count:
                    raise ArchiveValidationError(location, "ZIP chứa thành viên trùng lặp hoặc số lượng không khớp danh mục")
                files = {}
                data_offsets = {}
                total_size = 0
                next_offset = 0
                for member in sorted(members, key=lambda value: value.header_offset):
                    location = member.filename
                    if member.volume != 0:
                        raise ArchiveValidationError(location, "Không hỗ trợ thành viên ZIP nằm khác ổ đĩa")
                    mode = member.external_attr >> 16
                    if (member.orig_filename != member.filename or member.is_dir()
                            or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                            or member.flag_bits & ~0x800 or member.extra or member.comment
                            or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                        raise ArchiveValidationError(location, "Chỉ chấp nhận tệp thường không mã hóa, không metadata bổ sung, không có data descriptor")
                    # 中央目录可能故意漏掉本地成员；检查连续边界，禁止藏在目录之外的文件。
                    if member.header_offset != next_offset:
                        raise ArchiveValidationError(location, "ZIP chứa dữ liệu không có trong danh mục hoặc các tệp chồng lấn")
                    source.seek(next_offset)
                    header = source.read(30)
                    if len(header) != 30:
                        raise ArchiveValidationError(location, "Phần đầu tệp cục bộ của ZIP không hoàn chỉnh")
                    local = struct.unpack("<4s5H3L2H", header)
                    if (local[0] != b"PK\x03\x04" or local[2] != member.flag_bits
                            or local[3] != member.compress_type or local[6] != member.CRC
                            or local[7] != member.compress_size or local[8] != member.file_size
                            or local[10] != 0):
                        raise ArchiveValidationError(location, "Phần đầu tệp cục bộ của ZIP không khớp với danh mục")
                    if member.compress_type == zipfile.ZIP_STORED and member.compress_size != member.file_size:
                        raise ArchiveValidationError(location, "Độ dài byte của tệp chưa nén không khớp")
                    data_offsets[location] = next_offset + 30 + local[9]
                    next_offset += 30 + local[9] + member.compress_size
                    if member.filename == "manifest.json":
                        limit = MAX_MANIFEST_BYTES
                    elif member.filename in {f"collections/{name}.jsonl" for name in FACTION_BATCH_COLLECTIONS}:
                        limit = MAX_COLLECTION_BYTES
                    elif _COVER_PATH.fullmatch(member.filename):
                        limit = MAX_COVER_BYTES
                    else:
                        raise ArchiveValidationError(location, "Tệp không xác định hoặc đường dẫn không an toàn")
                    total_size += member.file_size
                    if member.file_size > limit or total_size > MAX_TOTAL_BYTES:
                        raise ArchiveValidationError(location, "Kích thước sau khi giải nén vượt quá giới hạn")
                    files[member.filename] = member
                if next_offset != offset:
                    raise ArchiveValidationError("archive", "ZIP chứa dữ liệu nằm ngoài danh mục")
                location = "manifest.json"
                if location not in files:
                    raise ArchiveValidationError(location, "Thiếu bản kê")
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
                    raise ArchiveValidationError(location, "Các trường của bản kê không đúng với phiên bản cố định")
                if (manifest.get("format") != FORMAT or type(manifest.get("format_version")) is not int
                        or manifest["format_version"] not in (FORMAT_VERSION, EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION)):
                    raise ArchiveValidationError(location, "Phiên bản định dạng sao lưu không xác định; chỉ hỗ trợ 1–14")
                version = manifest["format_version"]
                if version in (EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION):
                    keys.add("export_profile")
                if set(manifest) != keys:
                    raise ArchiveValidationError(location, "Các trường của bản kê không đúng với phiên bản cố định")
                if manifest["complete"] is not True or manifest["encoding"] != ENCODING:
                    raise ArchiveValidationError(location, "Bản sao lưu chưa hoàn tất hoặc tài liệu dùng mã hóa không được hỗ trợ")
                if not isinstance(manifest["source_revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_revision"]):
                    raise ArchiveValidationError(location, "Phiên bản mã nguồn phải là số commit Git đầy đủ")
                if not isinstance(manifest["novel_id"], str) or not re.fullmatch(r"[0-9a-f]{24}", manifest["novel_id"]):
                    raise ArchiveValidationError(location, "Định dạng ID tiểu thuyết không hợp lệ")
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
                    raise ArchiveValidationError(location, "Bản kê phải khai báo trung thực phạm vi và khoảng trống xác minh của phiên bản này")
                if version in (EXPORT_FORMAT_VERSION, REVISION_FORMAT_VERSION, FORESHADOWING_FORMAT_VERSION, CHAPTER_RECORD_FORMAT_VERSION, ITEM_OWNER_FORMAT_VERSION, CHARACTER_RELATION_STATE_FORMAT_VERSION, CHARACTER_FACT_FORMAT_VERSION, CHARACTER_RELATION_FACT_FORMAT_VERSION, ITEM_FACT_FORMAT_VERSION, FACTION_FACT_FORMAT_VERSION, CHARACTER_BATCH_FORMAT_VERSION, COMBINED_FORMAT_VERSION, FACTION_VOLUME_START_FORMAT_VERSION) and manifest["export_profile"] != EXPORT_PROFILE:
                    raise ArchiveValidationError(location, "Khai báo cách thức xuất không đáp ứng yêu cầu của phiên bản này")
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
                    raise ArchiveValidationError(location, "Các bộ sưu tập phải khớp toàn bộ danh sách trắng, kể cả bộ sưu tập trống")
                assets = manifest["assets"]
                if not isinstance(assets, list) or len(assets) > 1:
                    raise ArchiveValidationError(location, "Gói một cuốn sách chỉ được chứa ảnh bìa thực sự được tham chiếu")
                expected = {"manifest.json"}
                descriptors = []
                for name in names:
                    entry = collections[name]
                    if (not isinstance(entry, dict) or set(entry) != {"path", "count", "size_bytes", "sha256"}
                            or entry["path"] != f"collections/{name}.jsonl"
                            or type(entry["count"]) is not int or not 0 <= entry["count"] <= MAX_RECORDS):
                        raise ArchiveValidationError(location, f"Bộ sưu tập {name} có bản kê không hợp lệ")
                    descriptors.append(entry)
                for entry in assets:
                    if (not isinstance(entry, dict) or set(entry) != {"path", "size_bytes", "sha256"}
                            or not isinstance(entry["path"], str) or not _COVER_PATH.fullmatch(entry["path"])):
                        raise ArchiveValidationError(location, "Bản kê ảnh bìa không hợp lệ")
                    descriptors.append(entry)
                for entry in descriptors:
                    if (type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0
                            or not isinstance(entry["sha256"], str) or not _HEX64.fullmatch(entry["sha256"])):
                        raise ArchiveValidationError(location, "Định dạng độ dài tệp hoặc SHA256 không hợp lệ")
                    expected.add(entry["path"])
                if set(files) != expected:
                    raise ArchiveValidationError(location, "Có tệp không được khai báo hoặc thiếu tệp đã nêu trong bản kê")
                checked_files = [{"path": "manifest.json", "size_bytes": len(manifest_bytes),
                                  "sha256": hashlib.sha256(manifest_bytes).hexdigest()}]
                documents = {name: [] for name in names}
                cover_bytes = {}
                record_count = 0
                for entry in descriptors:
                    location = entry["path"]
                    member = files[location]
                    if entry["size_bytes"] != member.file_size:
                        raise ArchiveValidationError(location, "Độ dài tệp không khớp với bản kê")
                    digest = hashlib.sha256()
                    actual_size = 0
                    with bundle.open(member) as stream:
                        if location.startswith("collections/"):
                            name = location[len("collections/"):-len(".jsonl")]
                            while line := stream.readline(MAX_LINE_BYTES + 1):
                                line_number = len(documents[name]) + 1
                                line_location = f"{location}:{line_number}"
                                if len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
                                    raise ArchiveValidationError(line_location, "Tài liệu quá lớn hoặc cuối tệp thiếu LF, bản sao lưu có thể chưa hoàn tất")
                                digest.update(line)
                                actual_size += len(line)
                                record_count += 1
                                if record_count > MAX_RECORDS:
                                    raise ArchiveValidationError(line_location, "Tổng số tài liệu vượt quá giới hạn")
                                _, nodes = _parse_json(line, line_location)
                                json_nodes += nodes
                                if json_nodes > MAX_JSON_NODES:
                                    raise ArchiveValidationError(line_location, "Tổng số trường JSON trong gói vượt quá giới hạn")
                                documents[name].append(decode_document(line, line_location))
                            if len(documents[name]) != entry["count"]:
                                raise ArchiveValidationError(location, "Số lượng tài liệu không khớp với bản kê")
                        else:
                            cover_content = bytearray()
                            while chunk := stream.read(64 * 1024):
                                digest.update(chunk)
                                actual_size += len(chunk)
                                cover_content.extend(chunk)
                    if actual_size != entry["size_bytes"] or digest.hexdigest() != entry["sha256"]:
                        raise ArchiveValidationError(location, "SHA256 hoặc độ dài nội dung tệp không khớp với bản kê")
                    if location.startswith("static/") and _COVER_PATH.fullmatch(location)[1] != digest.hexdigest():
                        raise ArchiveValidationError(location, "Băm đường dẫn ảnh bìa không nhất quán với nội dung")
                    if location.startswith("static/"):
                        cover_bytes[location] = bytes(cover_content)
                    checked_files.append({key: entry[key] for key in ("path", "size_bytes", "sha256")})
                summary = validate_documents(documents, ObjectId(manifest["novel_id"]), format_version=version)
                if json.dumps(summary, sort_keys=True) != json.dumps(manifest["validation_summary"], sort_keys=True):
                    raise ArchiveValidationError("manifest.json:validation_summary", "ID nghiệp vụ và tóm tắt kiểm tra chuỗi cha không khớp với dữ liệu thực tế")
                cover = documents["novels"][0].get("cover_image")
                cover_paths = {entry["path"] for entry in assets}
                if cover in (None, ""):
                    if cover_paths:
                        raise ArchiveValidationError("manifest.json:assets", "Có ảnh bìa không được cuốn sách nào tham chiếu")
                elif not isinstance(cover, str) or not cover.startswith("/") or {cover[1:]} != cover_paths:
                    raise ArchiveValidationError("collections/novels.jsonl:1:cover_image", "Các tham chiếu ảnh bìa không nhất quán với tệp trong gói")
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
        raise ArchiveValidationError(location, "Không đọc được tệp, hoặc ZIP bị hỏng, không hoàn chỉnh") from exc


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
    parser = argparse.ArgumentParser(description="Xuất gói sao lưu một cuốn sách, xác minh ngoại tuyến, kiểm tra đích và khôi phục vào môi trường cô lập có xác nhận")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Kiểm tra chỉ đọc, không kết nối cơ sở dữ liệu")
    verify.add_argument("archive")
    export = commands.add_parser("export", help="Xuất chỉ đọc một cuốn sách từ cơ sở dữ liệu nguồn được chỉ định rõ")
    export.add_argument("--source-uri-env", required=True)
    export.add_argument("--source-database", required=True)
    export.add_argument("--novel-id", required=True)
    export.add_argument("--source-covers-dir", required=True)
    export.add_argument("--source-revision", required=True)
    export.add_argument("--output", required=True)
    dry_run = commands.add_parser("dry-run", help="Xác minh gói và quan sát đích chỉ đọc, không thực hiện khôi phục")
    dry_run.add_argument("archive")
    dry_run.add_argument("--target-uri-env", required=True)
    dry_run.add_argument("--target-database", required=True)
    dry_run.add_argument("--target-covers-dir", required=True)
    restore = commands.add_parser(
        "restore-empty", help="Khôi phục gói sách đã xác minh vào đích cô lập hoàn toàn mới được sử dụng độc quyền",
        description="Người vận hành phải sử dụng độc quyền cơ sở dữ liệu đích cô lập và thư mục ảnh bìa, bảo đảm không còn ứng dụng, chương trình bảo trì hay bên ghi nào khác đang truy cập.\nLệnh này không ngăn được client bên ngoài ghi vào và không cung cấp khóa an toàn ở cấp cơ sở dữ liệu.",
    )
    restore.add_argument("archive")
    restore.add_argument("--target-uri-env", required=True)
    restore.add_argument("--target-database", required=True)
    restore.add_argument("--target-covers-dir", required=True)
    restore.add_argument("--confirm-isolated-target", required=True, help="Phải trùng chính xác với tên cơ sở dữ liệu đích")
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
