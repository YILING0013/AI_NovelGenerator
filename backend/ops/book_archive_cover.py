"""把已验证的封面发布到操作者独占的目录；不打开备份包或访问数据库。"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from backend.ops.book_archive_contract import ArchiveValidationError


class ArchiveCoverError(ArchiveValidationError):
    """保存文件失败原因及是否已经发布或复用最终封面。"""

    def __init__(self, code: str, location: str, message: str, *, cover_state: str = "not_published") -> None:
        """记录固定错误码，避免错误信息带出本地路径。

        Args:
            code: 供恢复流程判断的固定错误码。
            location: 固定的失败步骤名称。
            message: 可直接告诉操作者的说明。
            cover_state: 本次操作截至失败时的封面状态。
        """
        super().__init__(location, message)
        self.code = code
        self.cover_state = cover_state


def validate_covers_directory(covers_dir: str | Path) -> Path:
    """确认操作者显式指定了现有普通封面目录。

    Args:
        covers_dir: 操作者必须独占的目录，不使用应用默认路径。
    Returns:
        目录的绝对路径；此检查不能阻止其它进程随后写入或替换目录。
    Raises:
        ArchiveCoverError: 目录缺失、不可访问或是链接。
    """
    if not str(covers_dir).strip():
        raise ArchiveCoverError("INVALID_INPUT", "target_covers_dir", "必须明确指定封面目录")
    try:
        directory = Path(covers_dir).absolute()
        observed = directory.lstat()
    except (OSError, ValueError):
        raise ArchiveCoverError("INVALID_INPUT", "target_covers_dir", "封面目录无效、缺失或不可访问") from None
    if (not stat.S_ISDIR(observed.st_mode) or stat.S_ISLNK(observed.st_mode)
            or getattr(observed, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ArchiveCoverError("INVALID_INPUT", "target_covers_dir", "封面目录必须是现有普通目录，不能是链接")
    return directory


def _verify_file(content: bytes, path: Path) -> None:
    """只读检查普通文件的身份和完整内容，供首次复用及重启复核共用。"""
    try:
        before = path.lstat()
    except FileNotFoundError:
        raise ArchiveCoverError("COVER_MISSING", "target_cover", "目标封面缺失") from None
    except OSError:
        raise ArchiveCoverError("COVER_CONFLICT", "target_cover", "无法检查目标封面") from None
    try:
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or before.st_size != len(content)):
            raise ArchiveCoverError("COVER_CONFLICT", "target_cover", "目标封面不是大小相同的普通文件")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            current = path.lstat()
            if (not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened)
                    or not os.path.samestat(opened, current) or stat.S_ISLNK(current.st_mode)
                    or getattr(current, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ArchiveCoverError("COVER_CONFLICT", "target_cover", "目标封面在打开时被替换")
            actual = stream.read(len(content) + 1)
            after = path.lstat()
            if (not os.path.samestat(opened, after) or not stat.S_ISREG(after.st_mode)
                    or getattr(after, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    or actual != content):
                raise ArchiveCoverError("COVER_CONFLICT", "target_cover", "目标封面内容不同或读取时被替换")
    except OSError:
        raise ArchiveCoverError("COVER_CONFLICT", "target_cover", "无法完整读取目标封面") from None


def verify_cover(content: bytes | None, entry: dict | None, *, covers_dir: str | Path) -> None:
    """只读复核已恢复封面，与本次验证后保留的包内字节完整比较。

    Args:
        content: 验证器保留的封面原始字节；没有封面时为 None。
        entry: 验证器保留的封面文件描述；没有封面时为 None。
        covers_dir: 操作者必须独占的现有普通目录。
    Returns:
        无；成功时没有创建、修改或删除任何文件。
    Raises:
        ArchiveCoverError: 目录不合格、封面缺失、文件类型或内容不同。
    """
    directory = validate_covers_directory(covers_dir)
    if entry is not None:
        _verify_file(content, directory / Path(entry["path"]).name)


def publish_cover(content: bytes | None, entry: dict | None, *, covers_dir: str | Path) -> str:
    """同步暂存已验证的封面，再通过不覆盖目标的硬链接发布或复用。

    Args:
        content: 验证器保留的封面原始字节；没有封面时为 None。
        entry: 验证器保留的封面文件描述；没有封面时为 None。
        covers_dir: 操作者必须独占的现有普通目录。
    Returns:
        not_needed、published 或 reused；发布不等于数据库已经提交。
    Raises:
        ArchiveCoverError: 文件检查、暂存、发布、同步或清理失败；状态保留发布事实。
    """
    directory = validate_covers_directory(covers_dir)
    if entry is None:
        return "not_needed"
    destination = directory / Path(entry["path"]).name
    try:
        _verify_file(content, destination)
    except ArchiveCoverError as exc:
        if exc.code != "COVER_MISSING":
            raise
    else:
        return "reused"

    state = "not_published"
    staging = None
    staging_stat = None
    location = "cover_staging"
    try:
        descriptor, staging_name = tempfile.mkstemp(prefix=".book-restore-cover-", suffix=".tmp", dir=directory)
        staging = Path(staging_name)
        with os.fdopen(descriptor, "wb") as stream:
            staging_stat = os.fstat(stream.fileno())
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        location = "cover_publish"
        try:
            # 目标在检查后出现时仍不能覆盖；相同内容可让两个恢复共用同一封面。
            os.link(staging, destination)
        except FileExistsError:
            _verify_file(content, destination)
            state = "reused"
        else:
            state = "published"
            location = "cover_sync"
            if os.name != "nt":
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        return state
    except ArchiveCoverError as exc:
        exc.cover_state = state
        raise
    except OSError:
        message = "封面已发布，但后续文件同步失败" if state == "published" else "封面暂存或硬链接发布失败，未覆盖目标文件"
        raise ArchiveCoverError("COVER_IO_FAILED", location, message, cover_state=state) from None
    finally:
        if staging is not None:
            try:
                current = staging.lstat()
                if (staging_stat is None or not os.path.samestat(staging_stat, current)
                        or not stat.S_ISREG(current.st_mode)
                        or getattr(current, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                    raise ArchiveCoverError("COVER_CLEANUP_FAILED", "cover_staging_cleanup", "临时文件已被替换，未清理该文件", cover_state=state)
                # 无论数据库是否提交，都只删本次确切临时文件，绝不删最终封面。
                staging.unlink()
            except OSError:
                raise ArchiveCoverError("COVER_CLEANUP_FAILED", "cover_staging_cleanup", "封面临时文件清理失败，最终封面保持原状", cover_state=state) from None
