"""把网页导出的原文同时保存在项目用户目录。"""
import os
from pathlib import Path
import re
import uuid
from fastapi import APIRouter, File, UploadFile
from backend.api.error_protocol import DomainApiError
from backend.storage import EXPORTS_DIR

router = APIRouter(prefix="/api/exports", tags=["exports"])
MAX_EXPORT_BYTES = 32 * 1024 * 1024


@router.post("")
async def save_export(file: UploadFile = File(...)):
    """保存独立导出副本，不覆盖同名文件或接受任意磁盘路径。

    Args: file: 用户正在导出的文件。
    Returns: 相对 user_data 的路径。
    """
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", file.filename or "export.txt").strip(" .")[:150]
    if not name or Path(name).stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}:
        name = "export.txt"
    content = await file.read(MAX_EXPORT_BYTES + 1)
    if len(content) > MAX_EXPORT_BYTES:
        raise DomainApiError("EXPORT_TOO_LARGE", "项目导出副本不能超过 32 MB，请使用浏览器另存。", status_code=413)
    folder = EXPORTS_DIR / uuid.uuid4().hex
    folder.mkdir(parents=True)
    with (folder / name).open("xb") as handle:
        handle.write(content); handle.flush(); os.fsync(handle.fileno())
    return {"path": f"exports/{folder.name}/{name}"}
