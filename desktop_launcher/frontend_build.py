"""校验前端内容哈希，只复用成功完成的生产构建。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BUILD_RECORD = "launcher-build.json"
_IGNORED_DIRS = {
    "node_modules", ".next", ".git", ".playwright-cli", "output",
    "playwright-report", "test-results", "coverage", ".vscode", ".idea",
}
_BUILD_FILES = (
    "BUILD_ID", "build-manifest.json", "routes-manifest.json",
    "prerender-manifest.json", "required-server-files.json",
)


def frontend_fingerprint(frontend_dir: Path, env: dict[str, str]) -> str:
    """计算前端文件、依赖和构建环境的内容哈希，包含未提交的修改。

    Args:
        frontend_dir: 前端项目目录。
        env: 实际传给编译进程的环境变量。

    Returns:
        SHA-256 哈希；后端文件和前端生成的缓存不参与计算。
    """
    node = subprocess.run(
        ["node", "--version"], cwd=frontend_dir, env=env, check=True,
        capture_output=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    build_env = {key: value for key, value in env.items() if key.startswith("NEXT_PUBLIC_")}
    build_env["NODE_ENV"] = "production"
    digest = hashlib.sha256(b"launcher-frontend-v1\0" + node.stdout.strip())
    digest.update(json.dumps(build_env, sort_keys=True).encode("utf-8"))
    files = []
    for directory, dirs, names in os.walk(frontend_dir):
        dirs[:] = sorted(name for name in dirs if name not in _IGNORED_DIRS)
        for name in sorted(names):
            if name == "next-env.d.ts" or name.endswith((".tsbuildinfo", ".md", ".log")):
                continue
            files.append(Path(directory) / name)
    # npm 记录的实际安装版本也参与校验，重新安装不同版本后不能复用旧构建。
    for name in ("node_modules/.package-lock.json", "node_modules/next/package.json"):
        path = frontend_dir / name
        if path.is_file():
            files.append(path)
    for path in files:
        digest.update(path.relative_to(frontend_dir).as_posix().encode("utf-8") + b"\0")
        with path.open("rb") as source:
            digest.update(hashlib.file_digest(source, "sha256").digest())
    return digest.hexdigest()


def frontend_build_is_current(frontend_dir: Path, fingerprint: str) -> bool:
    """检查记录的内容哈希和 Next.js 生产构建是否仍然匹配。

    Args:
        frontend_dir: 前端项目目录。
        fingerprint: 当前文件和环境的内容哈希。

    Returns:
        成功构建记录和必要产物都有效时返回 True。
    """
    output = frontend_dir / ".next"
    try:
        record = json.loads((output / BUILD_RECORD).read_text(encoding="utf-8"))
        build_id = (output / "BUILD_ID").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return False
    return (
        record == {"fingerprint": fingerprint, "build_id": build_id}
        and bool(build_id)
        and all((output / name).is_file() for name in _BUILD_FILES)
        and (output / "server").is_dir()
        and (output / "static").is_dir()
    )


def build_and_start_frontend(frontend_dir: Path, fingerprint: str, command: list[str]) -> int:
    """编译成功后记录哈希，再执行前端启动命令。

    Args:
        frontend_dir: 前端项目目录。
        fingerprint: 编译前计算的内容哈希。
        command: npm run start 及监听参数。

    Returns:
        编译或服务进程的退出码；编译失败不会启动服务。
    """
    record_path = frontend_dir / ".next" / BUILD_RECORD
    # 编译中断可能留下部分产物，开始前先撤销上次的成功记录。
    record_path.unlink(missing_ok=True)
    env = {**os.environ, "NODE_ENV": "production"}
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    code = subprocess.run(
        [command[0], "run", "build"], cwd=frontend_dir, env=env, creationflags=flags,
        stdout=sys.stdout, stderr=sys.stderr,
    ).returncode
    if code:
        return code
    if frontend_fingerprint(frontend_dir, env) == fingerprint:
        build_id = (frontend_dir / ".next" / "BUILD_ID").read_text(encoding="utf-8").strip()
        record_path.write_text(
            json.dumps({"fingerprint": fingerprint, "build_id": build_id}), encoding="utf-8",
        )
        print("[INFO] 前端编译成功，已记录内容哈希。", flush=True)
    else:
        print("[WARNING] 编译期间前端文件发生变化，下次启动将重新编译。", flush=True)
    return subprocess.run(
        command, cwd=frontend_dir, env=env, creationflags=flags,
        stdout=sys.stdout, stderr=sys.stderr,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(build_and_start_frontend(Path.cwd(), sys.argv[1], sys.argv[2:]))
