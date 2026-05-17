"""Novel Generator 启动器。"""

import atexit
import codecs
import locale
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Literal, TextIO

import customtkinter as ctk

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
LOGS_DIR = BASE_DIR / "logs"

BACKEND_PORT = 8000
FRONTEND_PORT = 3000

LOG_READ_CHUNK_SIZE = 4096
LOG_FLUSH_INTERVAL_MS = 80
LOG_FLUSH_BATCH_CHARS = 16000
MAX_LOG_CHARS = 220_000
RETAIN_LOG_CHARS = 160_000
MAX_PENDING_LOG_CHARS = 160_000
RETAIN_PENDING_LOG_CHARS = 90_000
MAX_LOG_FILES = 100

ServiceState = Literal["stopped", "starting", "running", "stopping"]

_LOG_DIR_LOCK = threading.Lock()


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def kill_port(port: int) -> bool:
    """终止占用指定端口的进程 (Windows)。"""
    if sys.platform != "win32":
        return False

    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                pid = parts[4]
                subprocess.run(
                    ["taskkill", "/PID", pid, "/T", "/F"],
                    check=False,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return True
    except Exception:
        pass

    return False


def wait_for_port_release(port: int, timeout: float = 3.0, interval: float = 0.2) -> bool:
    """后台轮询端口释放，避免阻塞 Tk 主线程。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_port_in_use(port):
            return True
        time.sleep(interval)
    return not is_port_in_use(port)


def ensure_logs_dir() -> Path:
    with _LOG_DIR_LOCK:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


def build_log_file_path(service_key: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return ensure_logs_dir() / f"{timestamp}_{service_key}.log"


def cleanup_old_log_files() -> None:
    """最多保留最近的日志文件，避免目录无限增长。"""
    with _LOG_DIR_LOCK:
        if not LOGS_DIR.exists():
            return

        log_files = sorted(LOGS_DIR.glob("*.log"), key=lambda path: path.stat().st_mtime)
        overflow = len(log_files) - MAX_LOG_FILES
        if overflow <= 0:
            return

        for path in log_files[:overflow]:
            try:
                path.unlink()
            except OSError:
                # 打开的日志文件或系统锁定文件直接跳过，避免影响当前启动流程。
                continue


class AdaptiveStreamDecoder:
    """增量解码子进程输出，兼容 UTF-8 与常见 Windows 编码。"""

    def __init__(self):
        seen: set[str] = set()
        self._encodings: list[str] = []
        for encoding in ("utf-8", "gbk", locale.getpreferredencoding(False)):
            normalized = (encoding or "").lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                self._encodings.append(encoding)

        self._buffer = bytearray()
        self._encoding: str | None = None
        self._decoder = None

    def _bind_decoder(self, encoding: str) -> None:
        self._encoding = encoding
        self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")

    def decode(self, chunk: bytes) -> str:
        if not chunk:
            return ""

        if self._decoder is not None:
            return self._decoder.decode(chunk, final=False)

        self._buffer.extend(chunk)
        for encoding in self._encodings:
            try:
                self._buffer.decode(encoding)
            except UnicodeDecodeError:
                continue

            self._bind_decoder(encoding)
            decoded = self._decoder.decode(bytes(self._buffer), final=False)
            self._buffer.clear()
            return decoded

        if len(self._buffer) < LOG_READ_CHUNK_SIZE * 2:
            return ""

        self._bind_decoder(self._encodings[0])
        decoded = self._decoder.decode(bytes(self._buffer), final=False)
        self._buffer.clear()
        return decoded

    def flush(self) -> str:
        if self._decoder is not None:
            tail = self._decoder.decode(b"", final=True)
            if self._buffer:
                tail += bytes(self._buffer).decode(self._encoding or self._encodings[0], errors="replace")
                self._buffer.clear()
            return tail

        if not self._buffer:
            return ""

        for encoding in self._encodings:
            try:
                decoded = self._buffer.decode(encoding)
                self._buffer.clear()
                return decoded
            except UnicodeDecodeError:
                continue

        decoded = self._buffer.decode(self._encodings[0], errors="replace")
        self._buffer.clear()
        return decoded


class ServicePanel(ctk.CTkFrame):
    """单个服务的控制面板与日志窗口。"""

    def __init__(
        self,
        master,
        service_key: str,
        title: str,
        command: list[str],
        cwd: Path,
        port: int,
        url: str,
        accent_color: str,
        env: dict[str, str] | None = None,
    ):
        super().__init__(
            master,
            corner_radius=18,
            border_width=1,
            border_color=("gray82", "gray22"),
            fg_color=("gray97", "gray10"),
        )
        self.service_key = service_key
        self.command = command
        self.cwd = str(cwd)
        self.env = env or {}
        self.port = port
        self.url = url
        self.accent_color = accent_color

        self._proc: subprocess.Popen | None = None
        self._monitor_thread: threading.Thread | None = None
        self._state: ServiceState = "stopped"
        self._shutdown = False
        self._state_lock = threading.Lock()

        self._log_chunks: deque[str] = deque()
        self._pending_char_count = 0
        self._displayed_char_count = 0
        self._log_lock = threading.Lock()

        self._event_queue: deque[tuple[str, object]] = deque()
        self._event_lock = threading.Lock()

        self._log_file: TextIO | None = None
        self._log_file_path: Path | None = None
        self._log_file_lock = threading.Lock()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        header.grid_columnconfigure(1, weight=1)

        title_group = ctk.CTkFrame(header, fg_color="transparent")
        title_group.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_group,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")

        self.status_badge = ctk.CTkLabel(
            title_group,
            text="已停止",
            corner_radius=999,
            padx=10,
            pady=4,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.status_badge.pack(side="left", padx=(10, 0))

        self.header_actions = ctk.CTkFrame(header, fg_color="transparent")
        self.header_actions.grid(row=0, column=1, sticky="e")

        self.log = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=("gray99", "gray7"),
            text_color=("gray15", "gray90"),
            corner_radius=14,
            border_width=1,
            border_color=("gray84", "gray18"),
            state="disabled",
            wrap="word",
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)

        primary_actions = ctk.CTkFrame(footer, fg_color="transparent")
        primary_actions.grid(row=0, column=0, sticky="w")

        secondary_actions = ctk.CTkFrame(footer, fg_color="transparent")
        secondary_actions.grid(row=0, column=1, sticky="e")

        self.start_btn = ctk.CTkButton(
            primary_actions,
            text="启动",
            width=92,
            height=34,
            fg_color=accent_color,
            hover_color=self._blend_color(accent_color, 0.86),
            command=self.start,
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ctk.CTkButton(
            primary_actions,
            text="停止",
            width=92,
            height=34,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.stop,
            state="disabled",
        )
        self.stop_btn.pack(side="left")

        self.clear_btn = ctk.CTkButton(
            secondary_actions,
            text="清空",
            width=92,
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=("gray74", "gray28"),
            text_color=("gray30", "gray72"),
            hover_color=("gray86", "gray18"),
            command=self.clear_log,
        )
        self.clear_btn.pack(side="left", padx=(0, 8))

        self.open_btn = ctk.CTkButton(
            secondary_actions,
            text="打开",
            width=92,
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=("gray74", "gray28"),
            text_color=("gray30", "gray72"),
            hover_color=("gray86", "gray18"),
            command=lambda: webbrowser.open(self.url),
        )
        self.open_btn.pack(side="left")

        self.set_command(command)
        self._apply_status("stopped")
        self.after(LOG_FLUSH_INTERVAL_MS, self._flush_ui_updates)

    @staticmethod
    def _blend_color(color: str, factor: float) -> str:
        color = color.lstrip("#")
        if len(color) != 6:
            return "#1f2937"

        channels = []
        for index in (0, 2, 4):
            value = int(color[index:index + 2], 16)
            channels.append(max(0, min(255, int(value * factor))))
        return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"

    def _format_command(self, command: list[str]) -> str:
        if not command:
            return "-"
        if sys.platform == "win32":
            return subprocess.list2cmdline(command)
        return shlex.join(command)

    def _queue_event(self, event_type: str, payload=None) -> None:
        with self._event_lock:
            self._event_queue.append((event_type, payload))

    def _queue_log(self, text: str) -> None:
        if not text:
            return

        with self._log_lock:
            self._log_chunks.append(text)
            self._pending_char_count += len(text)

            # 仅裁剪 UI 待渲染缓存，磁盘日志始终保留完整输出。
            if self._pending_char_count <= MAX_PENDING_LOG_CHARS:
                return

            while self._log_chunks and self._pending_char_count > RETAIN_PENDING_LOG_CHARS:
                removed = self._log_chunks.popleft()
                self._pending_char_count -= len(removed)

            notice = "\n[Launcher] 界面仅保留最近日志，完整输出请查看 /logs。\n"
            self._log_chunks.appendleft(notice)
            self._pending_char_count += len(notice)

    def _pop_log_batch(self, max_chars: int) -> str:
        batch: list[str] = []
        batch_chars = 0

        with self._log_lock:
            while self._log_chunks and batch_chars < max_chars:
                chunk = self._log_chunks.popleft()
                batch.append(chunk)
                batch_chars += len(chunk)
                self._pending_char_count -= len(chunk)

        return "".join(batch)

    def _apply_status(self, state: ServiceState) -> None:
        styles = {
            "stopped": {
                "label": "已停止",
                "badge_fg": ("gray86", "gray20"),
                "badge_text": ("gray40", "gray70"),
                "start": "normal",
                "stop": "disabled",
                "border": ("gray82", "gray22"),
            },
            "starting": {
                "label": "启动中",
                "badge_fg": ("#fef3c7", "#4a3410"),
                "badge_text": ("#92400e", "#fbbf24"),
                "start": "disabled",
                "stop": "disabled",
                "border": "#f59e0b",
            },
            "running": {
                "label": "运行中",
                "badge_fg": ("#dcfce7", "#0f3320"),
                "badge_text": (self.accent_color, self.accent_color),
                "start": "disabled",
                "stop": "normal",
                "border": self.accent_color,
            },
            "stopping": {
                "label": "停止中",
                "badge_fg": ("#ffedd5", "#46200f"),
                "badge_text": ("#c2410c", "#fb923c"),
                "start": "disabled",
                "stop": "disabled",
                "border": "#f97316",
            },
        }
        style = styles[state]
        self.status_badge.configure(
            text=style["label"],
            fg_color=style["badge_fg"],
            text_color=style["badge_text"],
        )
        self.start_btn.configure(state=style["start"])
        self.stop_btn.configure(state=style["stop"])
        self.configure(border_color=style["border"])

    def _should_autoscroll(self) -> bool:
        try:
            _, bottom = self.log.yview()
            return bottom >= 0.995
        except Exception:
            return True

    def _append_to_log(self, text: str) -> None:
        should_autoscroll = self._should_autoscroll()
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self._displayed_char_count += len(text)

        if self._displayed_char_count > MAX_LOG_CHARS:
            trim_chars = self._displayed_char_count - RETAIN_LOG_CHARS
            self.log.delete("1.0", f"1.0 + {trim_chars} chars")

            trim_notice = "[Launcher] 界面历史日志已裁剪，完整输出请查看 /logs。\n"
            self.log.insert("1.0", trim_notice)
            self._displayed_char_count = RETAIN_LOG_CHARS + len(trim_notice)

        if should_autoscroll:
            self.log.see("end")
        self.log.configure(state="disabled")

    def _flush_ui_updates(self) -> None:
        if not self.winfo_exists():
            return

        with self._event_lock:
            events = list(self._event_queue)
            self._event_queue.clear()

        for event_type, payload in events:
            if event_type == "status":
                self._apply_status(payload)

        batch = self._pop_log_batch(LOG_FLUSH_BATCH_CHARS)
        if batch:
            self._append_to_log(batch)

        self.after(LOG_FLUSH_INTERVAL_MS, self._flush_ui_updates)

    def _open_log_file(self) -> None:
        self._close_log_file()

        try:
            log_path = build_log_file_path(self.service_key)
            log_file = log_path.open("a", encoding="utf-8", buffering=1)
        except Exception as exc:
            self._queue_log(f"[Launcher] 创建日志文件失败: {exc}\n")
            return

        with self._log_file_lock:
            self._log_file = log_file
            self._log_file_path = log_path

        cleanup_old_log_files()
        self._write_file_only(f"[Launcher] started_at={datetime.now().isoformat(timespec='seconds')}\n")
        self._write_file_only(f"[Launcher] service={self.service_key}\n")
        self._write_file_only(f"[Launcher] cwd={self.cwd}\n")
        self._write_file_only(f"[Launcher] command={self._format_command(self.command)}\n\n")

    def _write_file_only(self, text: str) -> None:
        if not text:
            return

        with self._log_file_lock:
            if self._log_file is None:
                return

            try:
                self._log_file.write(text)
                self._log_file.flush()
            except OSError:
                return

    def _close_log_file(self) -> None:
        with self._log_file_lock:
            if self._log_file is not None:
                try:
                    self._log_file.close()
                except OSError:
                    pass
            self._log_file = None
            self._log_file_path = None

    def write_log(self, text: str) -> None:
        self._queue_log(text)
        self._write_file_only(text)

    def _read_stream(self, stream, stream_name: str) -> None:
        decoder = AdaptiveStreamDecoder()

        try:
            while True:
                # 按块读取 stdout/stderr，避免长文本无换行时把生产进程卡在管道缓冲区。
                if hasattr(stream, "read1"):
                    chunk = stream.read1(LOG_READ_CHUNK_SIZE)
                else:
                    chunk = stream.read(LOG_READ_CHUNK_SIZE)

                if not chunk:
                    break

                decoded = decoder.decode(chunk)
                if decoded:
                    self.write_log(decoded)
        except Exception as exc:
            self.write_log(f"\n[Launcher Error] 读取 {stream_name} 流异常: {exc}\n")
        finally:
            tail = decoder.flush()
            if tail:
                self.write_log(tail)

    def _monitor_process(self, proc: subprocess.Popen) -> None:
        stdout_thread = threading.Thread(
            target=self._read_stream,
            args=(proc.stdout, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stream,
            args=(proc.stderr, "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        code = proc.wait()
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

        self.write_log(f"\n--- 进程退出 (code {code}) ---\n")
        self._close_log_file()

        with self._state_lock:
            if self._proc is proc:
                self._proc = None
            self._state = "stopped"

        self._queue_event("status", "stopped")

    def _build_env(self) -> dict[str, str]:
        full_env = os.environ.copy()
        full_env.update(self.env)
        full_env["PYTHONIOENCODING"] = "utf-8"
        full_env["PYTHONUTF8"] = "1"
        return full_env

    def _start_worker(self) -> None:
        if self._shutdown:
            with self._state_lock:
                self._state = "stopped"
            self._queue_event("status", "stopped")
            return

        self._open_log_file()

        if is_port_in_use(self.port):
            self.write_log(f"[WARN] 端口 {self.port} 已被占用，正在终止残留进程...\n")
            kill_port(self.port)
            if not wait_for_port_release(self.port):
                self.write_log(f"[ERROR] 无法释放端口 {self.port}\n")
                self._close_log_file()
                with self._state_lock:
                    self._state = "stopped"
                self._queue_event("status", "stopped")
                return
            self.write_log(f"[INFO] 端口 {self.port} 已释放\n")

        kwargs = {
            "cwd": self.cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": False,
            "bufsize": 0,
            "env": self._build_env(),
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(self.command, **kwargs)
        except Exception as exc:
            self.write_log(f"[ERROR] 启动进程失败: {exc}\n")
            self._close_log_file()
            with self._state_lock:
                self._state = "stopped"
            self._queue_event("status", "stopped")
            return

        if self._shutdown:
            self._kill_proc(proc)
            self._close_log_file()
            with self._state_lock:
                self._state = "stopped"
            self._queue_event("status", "stopped")
            return

        with self._state_lock:
            self._proc = proc
            self._state = "running"

        self._queue_event("status", "running")
        self._monitor_thread = threading.Thread(target=self._monitor_process, args=(proc,), daemon=True)
        self._monitor_thread.start()

    def start(self) -> None:
        with self._state_lock:
            if self._state != "stopped":
                return
            self._state = "starting"

        self._apply_status("starting")
        threading.Thread(target=self._start_worker, daemon=True).start()

    def _kill_proc(self, proc: subprocess.Popen | None = None) -> None:
        target = proc
        if target is None:
            with self._state_lock:
                target = self._proc

        if target is None or target.poll() is not None:
            return

        pid = target.pid
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            target.wait(timeout=5)
        except Exception:
            try:
                target.kill()
            except Exception:
                pass

    def stop(self) -> None:
        with self._state_lock:
            proc = self._proc
            if self._state != "running" or proc is None:
                return
            self._state = "stopping"

        self._apply_status("stopping")
        threading.Thread(target=self._kill_proc, args=(proc,), daemon=True).start()

    def clear_log(self) -> None:
        with self._log_lock:
            self._log_chunks.clear()
            self._pending_char_count = 0

        self._displayed_char_count = 0
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def is_running(self) -> bool:
        with self._state_lock:
            return self._state == "running" and self._proc is not None and self._proc.poll() is None

    def force_cleanup(self) -> None:
        with self._state_lock:
            self._shutdown = True
            proc = self._proc

        if proc is None or proc.poll() is not None:
            self._close_log_file()
            return

        self._kill_proc(proc)

    def set_command(self, command: list[str]) -> None:
        self.command = command


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Novel Generator Launcher")
        self.geometry("1380x840")
        self.minsize(1080, 680)
        self.configure(fg_color=("gray95", "gray6"))

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

        toolbar = ctk.CTkFrame(
            self,
            corner_radius=18,
            border_width=1,
            border_color=("gray82", "gray22"),
            fg_color=("gray98", "gray11"),
        )
        toolbar.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        toolbar.grid_columnconfigure(1, weight=1)

        action_group = ctk.CTkFrame(toolbar, fg_color="transparent")
        action_group.grid(row=0, column=0, sticky="w", padx=16, pady=14)

        ctk.CTkButton(
            action_group,
            text="全部启动",
            width=120,
            height=36,
            fg_color="#15803d",
            hover_color="#166534",
            command=self.start_all,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            action_group,
            text="全部停止",
            width=120,
            height=36,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self.stop_all,
        ).pack(side="left")

        self.theme_selector = ctk.CTkSegmentedButton(
            toolbar,
            values=["系统", "浅色", "深色"],
            height=36,
            command=self._on_theme_mode_change,
        )
        self.theme_selector.grid(row=0, column=2, sticky="e", padx=16, pady=14)
        self.theme_selector.set("系统")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1, uniform="service")
        content.grid_columnconfigure(1, weight=1, uniform="service")

        self.backend = ServicePanel(
            content,
            service_key="backend",
            title="Backend",
            command=[str(VENV_PYTHON), "main.py"],
            cwd=BASE_DIR,
            port=BACKEND_PORT,
            url=f"http://localhost:{BACKEND_PORT}/docs",
            accent_color="#15803d",
        )
        self.backend.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.backend_debug = ctk.CTkCheckBox(
            self.backend.header_actions,
            text="调试日志",
            command=self._on_backend_debug_change,
        )
        self.backend_debug.pack(side="right")
        self._on_backend_debug_change()

        self.frontend = ServicePanel(
            content,
            service_key="frontend",
            title="Frontend",
            command=[],
            cwd=FRONTEND_DIR,
            port=FRONTEND_PORT,
            url=f"http://localhost:{FRONTEND_PORT}",
            accent_color="#2563eb",
        )
        self.frontend.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.frontend_mode = ctk.CTkSegmentedButton(
            self.frontend.header_actions,
            values=["生产模式", "开发模式"],
            height=30,
            command=self._on_frontend_mode_change,
        )
        self.frontend_mode.pack(side="right")
        self.frontend_mode.set("生产模式")
        self._on_frontend_mode_change("生产模式")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        atexit.register(self._atexit_cleanup)

    def _on_theme_mode_change(self, mode: str) -> None:
        mapping = {
            "系统": "system",
            "浅色": "light",
            "深色": "dark",
        }
        ctk.set_appearance_mode(mapping[mode])

    def _on_frontend_mode_change(self, mode: str) -> None:
        if mode == "生产模式":
            if sys.platform == "win32":
                cmd = ["cmd.exe", "/c", f"{self.npm_cmd} run build && {self.npm_cmd} run start"]
            else:
                cmd = ["sh", "-c", f"{self.npm_cmd} run build && {self.npm_cmd} run start"]
        else:
            cmd = [self.npm_cmd, "run", "dev"]

        self.frontend.set_command(cmd)
        if self.frontend.is_running():
            self.frontend.write_log("[INFO] 前端运行模式已切换，重启前端后生效。\n")

    def _build_backend_command(self) -> list[str]:
        cmd = [str(VENV_PYTHON), "main.py"]
        if self.backend_debug.get():
            cmd.append("--debug")
        return cmd

    def _on_backend_debug_change(self) -> None:
        self.backend.set_command(self._build_backend_command())
        if self.backend.is_running():
            self.backend.write_log("[INFO] 后端调试模式已切换，重启后端后生效。\n")

    def start_all(self) -> None:
        self.backend.start()
        self.frontend.start()

    def stop_all(self) -> None:
        self.backend.stop()
        self.frontend.stop()

    def _on_close(self) -> None:
        self.backend.force_cleanup()
        self.frontend.force_cleanup()
        self.destroy()

    def _atexit_cleanup(self) -> None:
        self.backend.force_cleanup()
        self.frontend.force_cleanup()


if __name__ == "__main__":
    App().mainloop()