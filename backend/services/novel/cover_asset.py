"""小说封面的安全解码、重编码与精确文件生命周期。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import tempfile
import warnings
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_COVER_BYTES = 2 * 1024 * 1024
MAX_COVER_DIMENSION = 4096
from backend.storage import COVERS_DIR as COVER_DIR

_COVER_URL_RE = re.compile(
    r"^/static/covers/(?P<digest>[0-9a-f]{64})(?P<extension>\.jpg|\.png|\.webp)$"
)
_FORMAT_TO_EXTENSION = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
_COVER_ASSET_LOCK = asyncio.Lock()


@dataclass(frozen=True, slots=True)
class EncodedCoverAsset:
    """已通过安全校验并重新编码的封面内容。"""

    content: bytes
    digest: str
    extension: str

    @property
    def url(self) -> str:
        """返回可持久化到小说文档的静态资源 URL。"""
        return f"/static/covers/{self.digest}{self.extension}"


async def read_and_encode_cover(upload: UploadFile) -> EncodedCoverAsset:
    """流式读取并安全重编码单帧小说封面。

    Args:
        upload: FastAPI 接收的上传文件；文件名和 Content-Type 均不作为格式依据。

    Returns:
        去除元数据、可按内容哈希落盘的封面对象。

    Raises:
        ValueError: 输入超过限制、格式不受支持、图像损坏或尺寸非法。
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(64 * 1024, MAX_COVER_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_COVER_BYTES:
            raise ValueError("封面文件不能超过 2 MiB")
    if total == 0:
        raise ValueError("封面文件不能为空")

    return await asyncio.to_thread(_encode_cover, b"".join(chunks))


def _encode_cover(content: bytes) -> EncodedCoverAsset:
    """使用 Pillow 校验完整像素并生成不携带原元数据的新文件。

    Args:
        content: 已完成输入大小限制的原始上传字节。

    Returns:
        格式、尺寸、帧数和存储大小均符合约束的封面对象。
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(
                io.BytesIO(content),
                formats=tuple(_FORMAT_TO_EXTENSION),
            ) as source:
                image_format = str(source.format or "").upper()
                if image_format not in _FORMAT_TO_EXTENSION:
                    raise ValueError("封面仅支持 JPEG、PNG 或 WebP")
                if int(getattr(source, "n_frames", 1)) != 1:
                    raise ValueError("封面必须是单帧图片")
                width, height = source.size
                if (
                    width < 1
                    or height < 1
                    or width > MAX_COVER_DIMENSION
                    or height > MAX_COVER_DIMENSION
                ):
                    raise ValueError("封面宽高必须位于 1 到 4096 像素之间")
                source.load()

                # 在移除 EXIF 前先把方向写入像素，否则手机竖图会在重编码后发生旋转。
                oriented = ImageOps.exif_transpose(source)
                has_alpha = "A" in oriented.getbands() or (
                    oriented.mode == "P" and "transparency" in oriented.info
                )
                if image_format == "JPEG":
                    clean_mode = "L" if oriented.mode == "L" else "RGB"
                else:
                    clean_mode = "RGBA" if has_alpha else "RGB"
                pixels = oriented.convert(clean_mode)

                # 新建像素画布而非直接 save 原 Image，确保 EXIF、文本块和 ICC 等元数据不被继承。
                sanitized = Image.new(clean_mode, pixels.size)
                sanitized.paste(pixels)

        output = io.BytesIO()
        if image_format == "JPEG":
            sanitized.save(output, format="JPEG", quality=90, optimize=True)
        elif image_format == "PNG":
            sanitized.save(output, format="PNG", optimize=True)
        else:
            sanitized.save(output, format="WEBP", quality=90, method=6)
        encoded = output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("封面解码像素数量超过安全限制") from exc
    except UnidentifiedImageError as exc:
        raise ValueError("无法识别封面图片格式") from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError("封面图片损坏或无法完整解码") from exc

    if len(encoded) > MAX_COVER_BYTES:
        raise ValueError("封面重新编码后不能超过 2 MiB")
    digest = hashlib.sha256(encoded).hexdigest()
    return EncodedCoverAsset(
        content=encoded,
        digest=digest,
        extension=_FORMAT_TO_EXTENSION[image_format],
    )


@asynccontextmanager
async def cover_asset_write_lock() -> AsyncIterator[None]:
    """串行化单进程内文件落盘、CAS 与无引用清理边界。

    Yields:
        已持有封面资产互斥锁的执行区间。
    """
    async with _COVER_ASSET_LOCK:
        yield


def store_cover_asset(asset: EncodedCoverAsset) -> bool:
    """在固定封面目录内 fsync 后原子保存重编码内容。

    Args:
        asset: 已通过解码和大小校验的封面对象。

    Returns:
        本次新建目标文件时返回 True；相同哈希文件已存在时返回 False。
    """
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    target = COVER_DIR / f"{asset.digest}{asset.extension}"
    if target.exists():
        return False

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".cover-",
        suffix=".tmp",
        dir=COVER_DIR,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(asset.content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    finally:
        # 仅清理本次明确创建的临时文件；成功 replace 后路径已不存在。
        if temporary_path.exists():
            temporary_path.unlink()
    return True


def remove_cover_asset(url: str | None) -> bool:
    """只删除符合项目内容哈希命名规则的一个明确封面文件。

    Args:
        url: 小说文档中的封面静态 URL。

    Returns:
        删除了现有安全目标时返回 True；URL 非法或文件不存在时返回 False。
    """
    match = _COVER_URL_RE.fullmatch(url or "")
    if match is None:
        return False
    target = COVER_DIR / f"{match.group('digest')}{match.group('extension')}"
    if not target.is_file():
        return False
    target.unlink()
    return True


__all__ = [
    "COVER_DIR",
    "EncodedCoverAsset",
    "MAX_COVER_BYTES",
    "MAX_COVER_DIMENSION",
    "cover_asset_write_lock",
    "read_and_encode_cover",
    "remove_cover_asset",
    "store_cover_asset",
]
