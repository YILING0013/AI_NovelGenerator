"""Novel Generator 启动器。"""

import atexit
import codecs
import errno
import json
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

from PySide6.QtCore import Qt, QRegularExpression, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QKeySequence, QPalette, QShortcut, QSyntaxHighlighter, QTextCursor
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from .logs import LogPreviewFilter
from .frontend_build import frontend_build_is_current, frontend_fingerprint
from .ui import IconButton, THEMES

from backend.runtime import (
    BACKEND_PORT_ENV_VAR,
    DEFAULT_BACKEND_PORT,
    DEFAULT_FRONTEND_PORT,
    FRONTEND_PORT_ENV_VAR,
    get_backend_port,
    get_frontend_port,
)
from .settings import (
    load_launcher_settings,
    save_launcher_settings,
    validate_launcher_settings,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
from backend.storage import LOGS_DIR
from backend.migrations import prepare_files, MigrationError

LOG_READ_CHUNK_SIZE = 4096
LOG_FLUSH_INTERVAL_MS = 80
LOG_FLUSH_BATCH_CHARS = 8192
LOG_FILE_FLUSH_INTERVAL_SECONDS = 1.0
LOG_FILE_FLUSH_BYTES = 64 * 1024
MAX_LOG_BLOCKS = 2000
MAX_LOG_CHARS = 220_000
RETAIN_LOG_CHARS = 160_000
MAX_PENDING_LOG_CHARS = 160_000
RETAIN_PENDING_LOG_CHARS = 90_000
MAX_LOG_FILES = 100
PROCESS_STOP_TIMEOUT_SECONDS = 5.0
THREAD_JOIN_TIMEOUT_SECONDS = 5.0

ServiceState = Literal["not_started", "starting", "compiling", "running", "stopping", "stop_failed", "stopped"]

_LOG_DIR_LOCK = threading.Lock()


def is_port_in_use(port: int) -> bool:
    """检查本机回环地址上是否已有服务接受连接。

    Args:
        port: 要检查的 TCP 端口。

    Returns:
        有服务监听时返回 True，否则返回 False。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def get_port_bind_error(port: int) -> str | None:
    """通过实际绑定探测端口是否可供新服务使用。

    Args:
        port: 要探测的 TCP 端口。

    Returns:
        端口可绑定时返回 None；被占用、系统保留或无权限时返回中文错误说明。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if winerror == 10013 or exc.errno in {errno.EACCES, errno.EPERM}:
                return f"端口 {port} 被 Windows 保留或当前账户无绑定权限，请在启动器中更换端口"
            if winerror == 10048 or exc.errno == errno.EADDRINUSE:
                return f"端口 {port} 已被其他服务占用，请先确认该服务或在启动器中更换端口"
            return f"端口 {port} 无法绑定：{exc}"
    return None


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
        """解码新字节，未收齐的字符留到下次。

        Args:
            chunk: 子进程输出的字节块。

        Returns:
            本次可以完整解码的文本。
        """
        if not chunk:
            return ""

        if self._decoder is not None:
            return self._decoder.decode(chunk, final=False)

        self._buffer.extend(chunk)
        for encoding in self._encodings:
            try:
                self._buffer.decode(encoding)
            except UnicodeDecodeError as exc:
                if encoding == "utf-8" and exc.reason == "unexpected end of data":
                    return ""
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
        """输出流结束时解码剩余字节。

        Returns:
            尚未返回的文本。
        """
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


class LogHighlighter(QSyntaxHighlighter):
    """仅检查短行头，为错误和警告着色。"""

    colors = THEMES["light"]

    def highlightBlock(self, text: str) -> None:
        """给当前日志行着色。

        Args:
            text: Qt 提供的当前行文本。

        Returns:
            无。
        """
        head = text[:220].upper()
        if any(word in head for word in ("ERROR", "TRACEBACK", "EXCEPTION", "[LLM 异常]")):
            self.setFormat(0, len(text), QColor(self.colors["error"]))
        elif any(word in head for word in ("WARNING", "WARN", "已截断", "已省略")):
            self.setFormat(0, len(text), QColor(self.colors["warning"]))


class ServicePanel(QWidget):
    """单个服务的控制按钮和有容量上限的日志窗口。"""

    def __init__(
        self, master, service_key: str, title: str, command: list[str],
        cwd: Path, port: int, url: str,
        env: dict[str, str] | None = None,
    ):
        super().__init__(master)
        self.setObjectName("servicePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.service_key = service_key
        self.command = command
        self.cwd = str(cwd)
        self.env = env or {}
        self.port = port
        self.url = url
        self._proc: subprocess.Popen | None = None
        self._monitor_thread: threading.Thread | None = None
        self._start_thread: threading.Thread | None = None
        self._stop_thread: threading.Thread | None = None
        self._stop_error: str | None = None
        self._state: ServiceState = "not_started"
        self._build_before_start = False
        self._shutdown = False
        self._state_lock = threading.Lock()
        self._log_chunks: deque[str] = deque()
        self._pending_char_count = 0
        self._log_lock = threading.Lock()
        self._event_queue: deque[tuple[str, object]] = deque()
        self._event_lock = threading.Lock()
        self._log_file: TextIO | None = None
        self._log_file_path: Path | None = None
        self._last_log_file_path: Path | None = None
        self._log_file_lock = threading.Lock()
        self._log_unflushed_bytes = 0
        self._log_flush_wakeup = threading.Event()
        self._log_close_requested = threading.Event()
        self._log_flush_thread: threading.Thread | None = None
        self._updating_log = False
        self._history_trimmed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_widget = QWidget()
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(20, 8, 20, 4)
        header.setSpacing(8)
        self.status_badge = QLabel()
        self.status_badge.setObjectName("serviceStatus")
        header.addWidget(self.status_badge)
        self.address_label = QLabel(f"127.0.0.1:{port}")
        self.address_label.setObjectName("muted")
        header.addWidget(self.address_label)
        header.addStretch()
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(12)
        header.addLayout(self.header_actions)
        header.addSpacing(8)
        self.run_btn = IconButton("play", "启动", show_text=True)
        self.run_btn.clicked.connect(self.toggle_running)
        header.addWidget(self.run_btn)
        layout.addWidget(header_widget)

        toolbar = QFrame()
        toolbar.setObjectName("logToolbar")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(20, 4, 20, 10)
        tools.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索日志  ·  Ctrl+F")
        self.search.setAccessibleName(f"搜索{title}日志")
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(256)
        self.search.setMaximumWidth(360)
        self.search.returnPressed.connect(self._find_next)
        tools.addWidget(self.search, 1)
        self.case_btn = QPushButton("Aa")
        self.regex_btn = QPushButton(".*")
        self.word_btn = QPushButton("ab")
        for button, label in ((self.case_btn, "区分大小写"), (self.regex_btn, "使用正则表达式"), (self.word_btn, "整词匹配")):
            button.setObjectName("searchOption")
            button.setCheckable(True)
            button.setFixedSize(36, 36)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.toggled.connect(self._clear_search_feedback)
            tools.addWidget(button)
        self.search.textChanged.connect(self._clear_search_feedback)
        self._last_search = None
        self._last_match = None
        find_btn = IconButton("next", "查找下一个（Enter）")
        find_btn.clicked.connect(self._find_next)
        tools.addWidget(find_btn)
        tools.addStretch()
        self.pause_btn = IconButton("pause", "暂停显示")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(lambda paused: self.pause_btn.set_action("play" if paused else "pause", "继续显示" if paused else "暂停显示"))
        tools.addWidget(self.pause_btn)
        self.follow_btn = IconButton("follow", "跟随最新日志")
        self.follow_btn.setCheckable(True)
        self.follow_btn.setChecked(True)
        self.follow_btn.toggled.connect(self._follow_latest)
        tools.addWidget(self.follow_btn)
        self.clear_btn = IconButton("clear", "清空显示")
        self.clear_btn.clicked.connect(self.clear_log)
        tools.addWidget(self.clear_btn)
        file_btn = IconButton("file", "打开当前日志文件")
        file_btn.clicked.connect(self._open_current_log)
        tools.addWidget(file_btn)
        layout.addWidget(toolbar)
        self.search_feedback = QLabel()
        self.search_feedback.setObjectName("searchFeedback")
        self.search_feedback.setWordWrap(True)
        self.search_feedback.hide()
        layout.addWidget(self.search_feedback)

        self.log = QPlainTextEdit()
        self.log.setObjectName("logView")
        self.log.setAccessibleName(f"{title}日志")
        self.log.setReadOnly(True)
        self.log.setUndoRedoEnabled(False)
        self.log.setMaximumBlockCount(MAX_LOG_BLOCKS)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setFont(QFont("Consolas", 10))
        self.log.setPlaceholderText("等待服务输出…")
        self.log.verticalScrollBar().valueChanged.connect(self._on_log_scroll)
        self.highlighter = LogHighlighter(self.log.document())
        layout.addWidget(self.log, 1)
        self.log_status = QLabel("0 字符")
        self.log_status.setObjectName("logStatus")
        layout.addWidget(self.log_status)
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.search.setFocus)
        self._apply_status("not_started")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._flush_ui_updates)
        self.timer.start(LOG_FLUSH_INTERVAL_MS)

    def _clear_search_feedback(self) -> None:
        self.search_feedback.clear()
        self.search_feedback.hide()
        self._last_search = None
        self._last_match = None

    def _find_next(self) -> None:
        needle = self.search.text()
        self.search_feedback.hide()
        if not needle:
            return
        pattern = needle if self.regex_btn.isChecked() else QRegularExpression.escape(needle)
        # Qt 的正则引擎支持限制回溯，复杂表达式不能耗尽界面线程。
        limits = "(*LIMIT_MATCH=10000)(*LIMIT_DEPTH=100)(*LIMIT_HEAP=1024)"
        if self.word_btn.isChecked():
            pattern = rf"(?<!\w)(?:{pattern})(?!\w)"
        options = QRegularExpression.PatternOption.UseUnicodePropertiesOption | QRegularExpression.PatternOption.MultilineOption
        if not self.case_btn.isChecked():
            options |= QRegularExpression.PatternOption.CaseInsensitiveOption
        expression = QRegularExpression(limits + pattern, options)
        if not expression.isValid():
            self.search_feedback.setText(f"正则表达式有误：{expression.errorString()}")
            self.search_feedback.show()
            return
        key = (needle, self.regex_btn.isChecked(), self.case_btn.isChecked(), self.word_btn.isChecked())
        cursor = self.log.textCursor()
        start = cursor.selectionEnd() if key == self._last_search else cursor.selectionStart()
        if key == self._last_search and self._last_match == (start, start):
            # 零宽匹配也向前移动一个完整字符，不能反复停在同一个位置。
            advance = QTextCursor(cursor)
            start = advance.position() if advance.movePosition(QTextCursor.MoveOperation.NextCharacter) else self.log.document().characterCount()
        text = self.log.toPlainText()
        match = expression.match(text, start) if start < self.log.document().characterCount() else expression.match(text)
        if match.isValid() and not match.hasMatch() and start > 0:
            match = expression.match(text)
        if not match.isValid():
            self.search_feedback.setText("这个正则表达式计算量过大，请简化后重试")
            self.search_feedback.show()
            return
        self._last_search = key
        if not match.hasMatch():
            self._last_match = None
            self.search_feedback.setText("当前显示的日志中没有匹配内容")
            self.search_feedback.show()
            return
        self.follow_btn.setChecked(False)
        cursor.setPosition(match.capturedStart())
        cursor.setPosition(match.capturedEnd(), QTextCursor.MoveMode.KeepAnchor)
        self.log.setTextCursor(cursor)
        self.log.ensureCursorVisible()
        self._last_match = (match.capturedStart(), match.capturedEnd())

    def _follow_latest(self, enabled: bool) -> None:
        if enabled:
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _on_log_scroll(self, value: int) -> None:
        if not self._updating_log and value < self.log.verticalScrollBar().maximum():
            self.follow_btn.setChecked(False)

    def _open_current_log(self) -> None:
        path = self._last_log_file_path or ensure_logs_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
            if self._pending_char_count <= MAX_PENDING_LOG_CHARS:
                return
            # 严格保留尾部，单个大块也不能越过上限；不会影响原始文件。
            while self._log_chunks and self._pending_char_count > RETAIN_PENDING_LOG_CHARS:
                chunk = self._log_chunks.popleft()
                excess = self._pending_char_count - RETAIN_PENDING_LOG_CHARS
                removed = min(len(chunk), excess)
                self._pending_char_count -= removed
                if removed < len(chunk):
                    self._log_chunks.appendleft(chunk[removed:])
            notice = "\n[Launcher] 界面仅保留最近日志，原文见日志文件。\n"
            self._log_chunks.appendleft(notice)
            self._pending_char_count += len(notice)

    def _pop_log_batch(self, max_chars: int) -> str:
        batch: list[str] = []
        batch_chars = 0
        with self._log_lock:
            while self._log_chunks and batch_chars < max_chars:
                chunk = self._log_chunks.popleft()
                take = min(len(chunk), max_chars - batch_chars)
                batch.append(chunk[:take])
                batch_chars += take
                self._pending_char_count -= take
                if take < len(chunk):
                    self._log_chunks.appendleft(chunk[take:])
        return "".join(batch)

    def _apply_status(self, state: ServiceState) -> None:
        labels = {
            "not_started": "未启动", "starting": "启动中", "compiling": "编译中",
            "running": "运行中", "stopping": "停止中", "stop_failed": "停止失败", "stopped": "已停止",
        }
        self.status_badge.setText("●  " + labels[state])
        self.status_badge.setProperty("state", state)
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        if state in {"not_started", "stopped"}:
            self.run_btn.set_action("play", "启动")
        else:
            self.run_btn.set_action("stop", "停止中" if state == "stopping" else "停止")
        self.run_btn.setEnabled(state != "stopping")
        tabs = self.window().findChild(QTabWidget)
        if tabs is not None:
            index = tabs.indexOf(self)
            if index >= 0:
                title = "后端日志" if self.service_key == "backend" else "前端日志"
                tabs.setTabText(index, f"{title}  ·  {labels[state]}")

    def _append_to_log(self, text: str) -> None:
        self._updating_log = True
        scrollbar = self.log.verticalScrollBar()
        previous_scroll = scrollbar.value()
        document = self.log.document()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # 只插入纯文本，HTML 和 data URI 永远不会作为页面或图片渲染。
        cursor.insertText(text)
        if document.blockCount() >= MAX_LOG_BLOCKS:
            self._history_trimmed = True
        if document.characterCount() > MAX_LOG_CHARS:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.setPosition(document.characterCount() - RETAIN_LOG_CHARS, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self._history_trimmed = True
        if self.follow_btn.isChecked():
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(previous_scroll)
        self._updating_log = False
        suffix = "  ·  旧日志已裁剪" if self._history_trimmed else ""
        self.log_status.setText(f"{document.characterCount() - 1:,} 字符  ·  {document.blockCount():,} 行{suffix}")

    def _flush_ui_updates(self) -> None:
        with self._event_lock:
            events = list(self._event_queue)
            self._event_queue.clear()
        if any(event_type == "status" for event_type, _ in events):
            # 停止或重启后，队列中的旧状态不能把界面改回去。
            self._apply_status(self.get_state())
        # 暂停只停止绘制，读管道和写文件继续；缓存仍然有上限。
        if not self.pause_btn.isChecked() and self.isVisible():
            batch = self._pop_log_batch(LOG_FLUSH_BATCH_CHARS)
            if batch:
                self._append_to_log(batch)

    def _open_log_file(self) -> None:
        self._close_log_file()

        try:
            log_path = build_log_file_path(self.service_key)
            log_file = log_path.open("a", encoding="utf-8", newline="", buffering=LOG_FILE_FLUSH_BYTES)
        except Exception as exc:
            self._queue_log(f"[Launcher] 创建日志文件失败: {exc}\n")
            return

        with self._log_file_lock:
            self._log_file = log_file
            self._log_file_path = log_path
            self._last_log_file_path = log_path
            self._log_unflushed_bytes = 0
            self._log_flush_wakeup = threading.Event()
            self._log_close_requested = threading.Event()
            self._log_flush_thread = threading.Thread(
                target=self._flush_log_file_periodically,
                args=(log_file, self._log_flush_wakeup),
                name=f"{self.service_key}-log-flush",
                daemon=True,
            )
            self._log_flush_thread.start()

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
                self._log_unflushed_bytes += len(text.encode("utf-8"))
                if self._log_unflushed_bytes >= LOG_FILE_FLUSH_BYTES:
                    self._log_flush_wakeup.set()
            except OSError as exc:
                self._disable_failed_log_file(exc)

    def _disable_failed_log_file(self, exc: OSError) -> None:
        """关闭写入失败的文件，仅向界面报告错误；调用方须持有文件锁。

        Args:
            exc: 写入或同步文件时发生的原始错误。

        Returns:
            无。
        """
        failed_file = self._log_file
        failed_path = self._log_file_path
        self._log_file = None
        self._log_file_path = None
        self._log_unflushed_bytes = 0
        self._log_flush_wakeup.set()
        self._queue_log(f"[Launcher] 写入日志失败: {failed_path}: {exc}\n")
        try:
            failed_file.close()
        except OSError as close_exc:
            self._queue_log(f"[Launcher] 关闭日志失败: {failed_path}: {close_exc}\n")

    def _flush_log_file_periodically(self, log_file: TextIO, wakeup: threading.Event) -> None:
        # 不依赖 Qt 定时器，窗口暂停绘制或暂时无响应时仍然保存日志。
        reported_error = None
        while True:
            wakeup.wait(LOG_FILE_FLUSH_INTERVAL_SECONDS)
            with self._log_file_lock:
                wakeup.clear()
                if self._log_file is not log_file:
                    return
                try:
                    if self._stop_error and self._stop_error != reported_error:
                        message = f"[ERROR] 停止失败：{self._stop_error}\n"
                        log_file.write(message)
                        self._log_unflushed_bytes += len(message.encode("utf-8"))
                        reported_error = self._stop_error
                    if self._log_unflushed_bytes:
                        log_file.flush()
                        os.fsync(log_file.fileno())
                        self._log_unflushed_bytes = 0
                except OSError as exc:
                    self._disable_failed_log_file(exc)
                    return
                if self._log_close_requested.is_set():
                    try:
                        log_file.close()
                    except OSError as exc:
                        self._queue_log(f"[Launcher] 关闭日志失败: {self._log_file_path}: {exc}\n")
                    self._log_file = None
                    self._log_file_path = None
                    return

    def _close_log_file(self) -> None:
        # 文件锁、flush、fsync 和 close 都可能等待磁盘，交给原日志线程完成。
        self._log_close_requested.set()
        self._log_flush_wakeup.set()
        flush_thread = self._log_flush_thread
        if flush_thread is not None:
            flush_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            if flush_thread.is_alive():
                raise TimeoutError("日志同步线程尚未结束，请稍后重试停止")
        self._log_flush_thread = None

    def write_log(self, text: str) -> None:
        """保存一条完整日志，并将截短后的文本送入界面。

        Args:
            text: 启动器产生的完整消息。

        Returns:
            无。
        """
        self._write_file_only(text)
        self._queue_log(LogPreviewFilter().feed(text, final=True))

    def _read_stream(self, stream, stream_name: str) -> None:
        decoder = AdaptiveStreamDecoder()
        preview = LogPreviewFilter()

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
                    self._write_file_only(decoded)
                    self._queue_log(preview.feed(decoded))
        except Exception as exc:
            self.write_log(f"\n[Launcher Error] 读取 {stream_name} 流异常: {exc}\n")
        finally:
            tail = decoder.flush()
            if tail:
                self._write_file_only(tail)
            self._queue_log(preview.feed(tail, final=True))
            stream.close()

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

        while True:
            # 进程创建后还可能在初始化或编译；开始接受连接才算运行中。
            if self.get_state() in {"starting", "compiling"} and is_port_in_use(self.port):
                with self._state_lock:
                    if self._state in {"starting", "compiling"} and proc.poll() is None:
                        self._state = "running"
                        self._queue_event("status")
            try:
                code = proc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                continue
        deadline = time.monotonic() + THREAD_JOIN_TIMEOUT_SECONDS
        reported = False
        while stdout_thread.is_alive() or stderr_thread.is_alive():
            stdout_thread.join(timeout=0.1)
            stderr_thread.join(timeout=0.1)
            if not reported and time.monotonic() >= deadline:
                self._report_stop_failure("服务进程已退出，但日志管道仍未关闭；请检查仍在运行的子进程后重试停止")
                reported = True

        self.write_log(f"\n--- 进程退出 (code {code}) ---\n")
        try:
            self._close_log_file()
        except TimeoutError as exc:
            self._report_stop_failure(str(exc))
            return

        with self._state_lock:
            if self._proc is proc:
                self._proc = None
                if self._state != "stopping":
                    self._state = "stopped"

        self._queue_event("status", "stopped")

    def _build_env(self) -> dict[str, str]:
        full_env = os.environ.copy()
        full_env.update(self.env)
        full_env["PYTHONIOENCODING"] = "utf-8"
        full_env["PYTHONUTF8"] = "1"
        # Popen 的 bufsize 只控制读取端，Python 子进程也必须及时交出输出。
        full_env["PYTHONUNBUFFERED"] = "1"
        return full_env

    def _fail_start(self, message: str) -> None:
        self.write_log(f"[ERROR] {message}\n")
        self._close_log_file()
        with self._state_lock:
            self._state = "stopped"
        self._queue_event("status", "stopped")

    def _start_worker(self) -> None:
        if self._shutdown or self.get_state() == "stopping":
            with self._state_lock:
                self._state = "stopped"
            self._queue_event("status", "stopped")
            return

        self._open_log_file()

        if is_port_in_use(self.port):
            self._fail_start(
                f"端口 {self.port} 已有服务监听。启动器不会自动终止未知进程，请复用现有服务或更换端口。"
            )
            return

        # connect_ex 无法识别 Windows 排除端口，必须实际 bind 才能提前捕获 WinError 10013。
        bind_error = get_port_bind_error(self.port)
        if bind_error:
            self._fail_start(bind_error)
            return

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

        else:
            kwargs["start_new_session"] = True

        try:
            command = list(self.command)
            if self.service_key == "frontend" and self._build_before_start:
                frontend_dir = Path(self.cwd)
                kwargs["env"]["NODE_ENV"] = "production"
                self.write_log("[INFO] 正在校验前端内容哈希…\n")
                fingerprint = frontend_fingerprint(frontend_dir, kwargs["env"])
                if frontend_build_is_current(frontend_dir, fingerprint):
                    self.write_log("[INFO] 前端内容哈希一致，复用上次编译，跳过编译。\n")
                    with self._state_lock:
                        if self._state != "stopping":
                            self._state = "starting"
                    self._queue_event("status")
                else:
                    self.write_log("[INFO] 前端内容有变化或缺少有效构建，开始编译。\n")
                    command = [
                        str(VENV_PYTHON), str(Path(__file__).with_name("frontend_build.py")),
                        fingerprint, *command,
                    ]
            if self._shutdown or self.get_state() == "stopping":
                self._fail_start("已取消启动。")
                return
            proc = subprocess.Popen(command, **kwargs)
        except Exception as exc:
            self.write_log(f"[ERROR] 启动进程失败: {exc}\n")
            self._close_log_file()
            with self._state_lock:
                self._state = "stopped"
            self._queue_event("status", "stopped")
            return

        should_kill = False
        with self._state_lock:
            # 关闭信号与进程登记必须处于同一临界区，避免窗口关闭后漏掉刚创建的子进程。
            self._proc = proc
            if self._shutdown or self._state == "stopping":
                should_kill = True

        self._monitor_thread = threading.Thread(target=self._monitor_process, args=(proc,), daemon=True)
        self._monitor_thread.start()
        if should_kill:
            self._kill_proc(proc)

    def toggle_running(self) -> None:
        """根据当前状态启动或停止服务。"""
        if self.get_state() in {"starting", "compiling", "running", "stop_failed"}:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        """在后台启动服务；重复点击不会创建额外进程。"""
        with self._state_lock:
            if self._state not in {"not_started", "stopped"}:
                return
            if any(worker is not None and worker.is_alive() for worker in (self._start_thread, self._stop_thread)):
                return
            self._shutdown = False
            self._stop_error = None
            self._state = "compiling" if self._build_before_start else "starting"

        self._apply_status(self.get_state())
        self._start_thread = threading.Thread(target=self._start_worker, daemon=True)
        self._start_thread.start()

    def _report_stop_failure(self, message: str) -> None:
        """保留进程和日志归属，并让停止按钮可重试。Args: message 失败原因。Returns: 无。"""
        with self._state_lock:
            self._state = "stop_failed"
            self._stop_error = message
        # 先让界面知道失败；磁盘阻塞时不能为了记录错误再次卡住收尾。
        self._queue_log(f"[ERROR] 停止失败：{message}\n")
        self._queue_event("status")
        self._log_flush_wakeup.set()

    def _kill_proc(self, proc: subprocess.Popen | None = None) -> bool:
        target = proc
        if target is None:
            with self._state_lock:
                target = self._proc

        if target is None or target.poll() is not None:
            return True

        pid = target.pid
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=True,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=PROCESS_STOP_TIMEOUT_SECONDS,
                )
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            try:
                target.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                if sys.platform == "win32":
                    raise
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                target.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as exc:
            self._report_stop_failure(f"PID {pid}：{exc}；请检查权限或进程状态后重试")
            return False
        return True

    def stop(self) -> None:
        """在后台停止本面板启动的服务及其子进程。"""
        with self._state_lock:
            if self._state not in {"starting", "compiling", "running", "stop_failed"}:
                return
            if self._stop_thread is not None and self._stop_thread.is_alive():
                return
            self._state = "stopping"

        self._apply_status("stopping")
        self._stop_thread = threading.Thread(target=self.force_cleanup, daemon=True)
        self._stop_thread.start()

    def clear_log(self) -> None:
        """清空当前预览和待显示缓存，保留日志文件。"""
        with self._log_lock:
            self._log_chunks.clear()
            self._pending_char_count = 0

        self._history_trimmed = False
        self._clear_search_feedback()
        self.log.clear()
        self.log_status.setText("0 字符")

    def is_running(self) -> bool:
        """返回服务进程是否存活，包括初始化、编译和停止期间。"""
        with self._state_lock:
            return self._proc is not None and self._proc.poll() is None

    def is_stopped(self) -> bool:
        """返回服务面板是否处于可重新配置的停止状态。

        Args:
            无。

        Returns:
            未启动或已停止时返回 True。
        """
        with self._state_lock:
            return self._state in {"not_started", "stopped"}

    def get_state(self) -> ServiceState:
        """返回服务面板当前的线程安全状态快照。

        Args:
            无。

        Returns:
            未启动、启动中、编译中、运行中、停止中、停止失败或已停止对应的状态值。
        """
        with self._state_lock:
            return self._state

    def configure_runtime(self, *, port: int, url: str, env: dict[str, str]) -> bool:
        """在服务停止时同步更新监听端口、打开地址和子进程环境。

        Args:
            port: 服务下次启动时使用的监听端口。
            url: 面板“打开”按钮访问的地址。
            env: 启动子进程时注入的环境变量。

        Returns:
            更新成功返回 True；服务未停止时返回 False。
        """
        with self._state_lock:
            if self._state not in {"not_started", "stopped"}:
                return False
            self.port = port
            self.url = url
            self.env = dict(env)
        self.address_label.setText(f"127.0.0.1:{port}")
        return True

    def force_cleanup(self) -> bool:
        """限时停止本面板的进程和日志线程。Args: 无。Returns: 全部收尾成功时为 True。"""
        with self._state_lock:
            self._shutdown = True
            if self._state not in {"not_started", "stopped"}:
                self._state = "stopping"
        self._queue_event("status")
        # 先等启动登记完成；超时仍保留取消信号，迟到的进程也会登记并停止。
        for worker in (self._start_thread, self._stop_thread):
            if worker is not None and worker is not threading.current_thread():
                worker.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
                if worker.is_alive():
                    self._report_stop_failure("启动或停止线程尚未结束，请稍后重试")
                    return False

        if not self._kill_proc():
            return False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
            if self._monitor_thread.is_alive():
                self._report_stop_failure("进程或日志管道尚未结束，请检查日志后重试停止")
                return False
        try:
            self._close_log_file()
        except TimeoutError as exc:
            self._report_stop_failure(str(exc))
            return False
        with self._state_lock:
            self._proc = None
            self._state = "stopped"
        self._queue_event("status")
        return True

    def set_command(self, command: list[str], *, build_before_start: bool = False) -> None:
        """设置下次启动的命令。

        Args:
            command: 可执行程序和参数。
            build_before_start: 命令是否先编译再启动服务。

        Returns:
            无。
        """
        self.command = command
        self._build_before_start = build_before_start


class App(QMainWindow):
    """Qt 启动器窗口，复用现有的服务命令和端口设置。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Novel Generator · 启动器")
        self.resize(1120, 760)
        self.setMinimumSize(760, 540)
        self._closing = False
        self._cleanup_done = threading.Event()
        self._cleanup_finished = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._cleanup_error: str | None = None
        self._preflight_active = False
        self._preflight_thread: threading.Thread | None = None
        self._preflight_proc: subprocess.Popen | None = None
        self._preflight_lock = threading.Lock()
        self._preflight_cancelled = threading.Event()
        self._preflight_events = deque()
        self._preflight_targets = ()
        self._backend_debug_enabled = False
        self._backend_debug_reply: QNetworkReply | None = None
        self._network = QNetworkAccessManager(self)
        self._network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        warnings: list[str] = []
        try:
            default_backend_port = get_backend_port()
        except ValueError as exc:
            default_backend_port = DEFAULT_BACKEND_PORT
            warnings.append(str(exc))
        try:
            default_frontend_port = get_frontend_port()
        except ValueError as exc:
            default_frontend_port = DEFAULT_FRONTEND_PORT
            warnings.append(str(exc))

        try:
            settings, settings_warning = load_launcher_settings(default_backend_port, default_frontend_port)
        except ValueError as exc:
            # 环境变量彼此冲突时仍要保证启动器能够打开，并继续尝试读取有效的持久化设置。
            warnings.append(f"环境变量端口配置无效：{exc}")
            settings, settings_warning = load_launcher_settings(DEFAULT_BACKEND_PORT, DEFAULT_FRONTEND_PORT)
        if settings_warning:
            warnings.append(settings_warning)
        self.backend_port = settings.backend_port
        self.frontend_port = settings.frontend_port
        self._applied_settings = settings

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topBar")
        heading = QHBoxLayout(topbar)
        heading.setContentsMargins(20, 10, 20, 10)
        heading.setSpacing(6)
        title = QLabel("Novel Generator")
        title.setObjectName("appTitle")
        heading.addWidget(title)
        heading.addSpacing(14)
        backend_label = QLabel("后端")
        heading.addWidget(backend_label)
        self.backend_port_entry = QLineEdit(str(self.backend_port))
        backend_label.setBuddy(self.backend_port_entry)
        self.backend_port_entry.setAccessibleName("后端端口")
        self.backend_port_entry.setToolTip("后端端口")
        self.backend_port_entry.setFixedWidth(68)
        self.backend_port_entry.setMaxLength(5)
        heading.addWidget(self.backend_port_entry)
        heading.addSpacing(6)
        frontend_label = QLabel("前端")
        heading.addWidget(frontend_label)
        self.frontend_port_entry = QLineEdit(str(self.frontend_port))
        frontend_label.setBuddy(self.frontend_port_entry)
        self.frontend_port_entry.setAccessibleName("前端端口")
        self.frontend_port_entry.setToolTip("前端端口")
        self.frontend_port_entry.setFixedWidth(68)
        self.frontend_port_entry.setMaxLength(5)
        heading.addWidget(self.frontend_port_entry)
        self.apply_ports_button = IconButton("save", "保存端口")
        self.apply_ports_button.clicked.connect(self._apply_port_settings)
        heading.addWidget(self.apply_ports_button)
        heading.addStretch()
        self.run_all_btn = IconButton("play", "全部启动", show_text=True, primary=True)
        self.run_all_btn.clicked.connect(self._toggle_all)
        heading.addWidget(self.run_all_btn)
        open_logs = IconButton("folder", "打开日志目录")
        open_logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ensure_logs_dir()))))
        heading.addWidget(open_logs)
        self._theme_mode = "系统"
        self.theme_btn = IconButton("system", "切换配色")
        self.theme_btn.clicked.connect(lambda: self._on_theme_mode_change({"系统": "浅色", "浅色": "深色", "深色": "系统"}[self._theme_mode]))
        heading.addWidget(self.theme_btn)
        layout.addWidget(topbar)
        self.port_status_label = QLabel("；".join(warnings))
        self.port_status_label.setObjectName("portFeedback")
        self.port_status_label.setWordWrap(True)
        self.port_status_label.setVisible(bool(warnings))
        layout.addWidget(self.port_status_label)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        web_links = QWidget()
        web_layout = QHBoxLayout(web_links)
        web_layout.setContentsMargins(0, 0, 20, 0)
        web_layout.setSpacing(4)
        self.api_docs_btn = QPushButton("API 文档")
        self.frontend_page_btn = QPushButton("前端网页")
        for button in (self.api_docs_btn, self.frontend_page_btn):
            button.setObjectName("textLink")
            button.setMinimumHeight(36)
            web_layout.addWidget(button)
        self.api_docs_btn.clicked.connect(lambda: webbrowser.open(self.backend.url))
        self.frontend_page_btn.clicked.connect(lambda: webbrowser.open(self.frontend.url))
        self.tabs.setCornerWidget(web_links, Qt.Corner.TopRightCorner)
        layout.addWidget(self.tabs, 1)
        self.backend = ServicePanel(
            self.tabs, service_key="backend", title="后端", command=[str(VENV_PYTHON), "main.py"],
            cwd=BASE_DIR, port=self.backend_port, url=f"http://127.0.0.1:{self.backend_port}/docs",
            env={BACKEND_PORT_ENV_VAR: str(self.backend_port), FRONTEND_PORT_ENV_VAR: str(self.frontend_port)},
        )
        self.tabs.addTab(self.backend, "后端日志  ·  未启动")
        self.backend_debug = IconButton("bug", "调试日志", show_text=True)
        self.backend_debug.setCheckable(True)
        self.backend_debug.toggled.connect(self._on_backend_debug_change)
        self.backend.header_actions.addWidget(self.backend_debug)
        self._on_backend_debug_change()
        self.frontend = ServicePanel(
            self.tabs, service_key="frontend", title="前端", command=[], cwd=FRONTEND_DIR,
            port=self.frontend_port, url=f"http://127.0.0.1:{self.frontend_port}",
            env={"NEXT_PUBLIC_API_BASE": f"http://127.0.0.1:{self.backend_port}"},
        )
        self.tabs.addTab(self.frontend, "前端日志  ·  未启动")
        self.frontend_mode = QComboBox()
        self.frontend_mode.addItems(["生产模式", "开发模式"])
        self.frontend_mode.currentTextChanged.connect(self._on_frontend_mode_change)
        self.frontend.header_actions.addWidget(self.frontend_mode)
        self._on_frontend_mode_change("生产模式", announce=False)
        # 每个启动入口都先保存端口输入，避免显示值和实际监听端口不同。
        self.backend.run_btn.clicked.disconnect()
        self.backend.run_btn.clicked.connect(lambda: self._toggle_service(self.backend, "后端"))
        self.frontend.run_btn.clicked.disconnect()
        self.frontend.run_btn.clicked.connect(lambda: self._toggle_service(self.frontend, "前端"))
        self._port_controls_enabled: bool | None = None
        self.control_timer = QTimer(self)
        self.control_timer.timeout.connect(self._sync_port_controls)
        self.control_timer.start(250)
        self._sync_port_controls()
        self._on_theme_mode_change("系统")
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            lambda: self._on_theme_mode_change(self._theme_mode)
        )
        atexit.register(self._atexit_cleanup)

    def _set_port_status(self, message: str, level: str = "info") -> None:
        self.port_status_label.setText(message)
        self.port_status_label.setVisible(bool(message))
        self.port_status_label.setProperty("level", level)
        self.port_status_label.style().unpolish(self.port_status_label)
        self.port_status_label.style().polish(self.port_status_label)

    def _sync_port_controls(self) -> None:
        self._poll_preflight()
        if self._closing:
            if self._cleanup_done.is_set():
                self.close()
                return
            if not self._cleanup_finished.is_set():
                return
            self._closing = False
            self.centralWidget().setEnabled(True)
            self._set_port_status(f"关闭失败：{self._cleanup_error}。请检查日志后重试停止或关闭。", "error")
        enabled = not self._preflight_active and self.backend.is_stopped() and self.frontend.is_stopped()
        if enabled != self._port_controls_enabled:
            self.backend_port_entry.setEnabled(enabled)
            self.frontend_port_entry.setEnabled(enabled)
            self.apply_ports_button.setEnabled(enabled)
            self._port_controls_enabled = enabled
        states = (self.backend.get_state(), self.frontend.get_state())
        self.backend_debug.setEnabled(
            not self._preflight_active and states[0] in {"not_started", "stopped", "running"} and self._backend_debug_reply is None
        )
        if self._preflight_active:
            action = ("play", "检查中")
        elif "stopping" in states:
            action = ("stop", "停止中")
        elif any(state in {"starting", "compiling", "running", "stop_failed"} for state in states):
            action = ("stop", "全部停止")
        else:
            action = ("play", "全部启动")
        if self.run_all_btn.text() != action[1]:
            self.run_all_btn.set_action(*action)
        self.run_all_btn.setEnabled(not self._preflight_active and "stopping" not in states)
        self.frontend_mode.setEnabled(not self._preflight_active)
        for service in (self.backend, self.frontend):
            service.run_btn.setEnabled(not self._preflight_active and service.get_state() != "stopping")

    def _apply_port_settings(self) -> bool:
        if self._preflight_active or not self.backend.is_stopped() or not self.frontend.is_stopped():
            self._set_port_status("请先停止前后端服务，再修改端口", "error")
            return False

        try:
            settings = validate_launcher_settings(self.backend_port_entry.text(), self.frontend_port_entry.text())
        except ValueError as exc:
            self._set_port_status(str(exc), "error")
            return False

        for label, port in (("后端", settings.backend_port), ("前端", settings.frontend_port)):
            if is_port_in_use(port):
                self._set_port_status(
                    f"{label}端口 {port} 已有外部服务监听；请先停止它，启动器不会自动终止未知进程",
                    "error",
                )
                return False
            bind_error = get_port_bind_error(port)
            if bind_error:
                self._set_port_status(bind_error, "error")
                return False

        try:
            save_launcher_settings(settings)
        except OSError as exc:
            self._set_port_status(f"端口设置保存失败：{exc}", "error")
            return False

        backend_configured = self.backend.configure_runtime(
            port=settings.backend_port,
            url=f"http://127.0.0.1:{settings.backend_port}/docs",
            env={
                BACKEND_PORT_ENV_VAR: str(settings.backend_port),
                FRONTEND_PORT_ENV_VAR: str(settings.frontend_port),
            },
        )
        frontend_configured = self.frontend.configure_runtime(
            port=settings.frontend_port,
            url=f"http://127.0.0.1:{settings.frontend_port}",
            env={"NEXT_PUBLIC_API_BASE": f"http://127.0.0.1:{settings.backend_port}"},
        )
        if not backend_configured or not frontend_configured:
            self._set_port_status("服务状态已变化，请停止服务后重试", "error")
            return False

        self.backend_port = settings.backend_port
        self.frontend_port = settings.frontend_port
        self._applied_settings = settings
        self._on_frontend_mode_change(self.frontend_mode.currentText(), announce=False)
        self._set_port_status(
            f"设置已保存：后端 {self.backend_port} / 前端 {self.frontend_port}",
            "success",
        )
        return True

    def _ensure_port_settings_applied(self) -> bool:
        try:
            requested = validate_launcher_settings(self.backend_port_entry.text(), self.frontend_port_entry.text())
        except ValueError as exc:
            self._set_port_status(str(exc), "error")
            return False
        if requested == self._applied_settings:
            return True
        return self._apply_port_settings()

    def _service_can_start(self, service: ServicePanel, label: str) -> bool:
        state = service.get_state()
        if state == "stopping":
            self._set_port_status(f"{label}服务正在停止，请等待状态变为已停止后再启动", "error")
            return False
        if state in {"starting", "compiling", "running"}:
            return True
        if is_port_in_use(service.port):
            self._set_port_status(
                f"{label}端口 {service.port} 已有外部服务监听；请先停止它或更换端口",
                "error",
            )
            return False
        bind_error = get_port_bind_error(service.port)
        if bind_error:
            self._set_port_status(bind_error, "error")
            return False
        return True

    def _on_theme_mode_change(self, mode: str) -> None:
        self._theme_mode = mode
        symbols = {"系统": "system", "浅色": "sun", "深色": "moon"}
        next_mode = {"系统": "浅色", "浅色": "深色", "深色": "系统"}[mode]
        self.theme_btn.set_action(symbols[mode], f"当前：{mode}主题；点击切换为{next_mode}")
        dark = mode == "深色" or (mode == "系统" and QApplication.instance().styleHints().colorScheme() == Qt.ColorScheme.Dark)
        c = THEMES["dark" if dark else "light"]
        # 下拉箭头等由 Qt 绘制的部分也使用相同配色。
        palette = self.palette()
        for role, token in (
            (QPalette.ColorRole.Window, "background"), (QPalette.ColorRole.WindowText, "text"),
            (QPalette.ColorRole.Base, "surface"), (QPalette.ColorRole.Text, "text"),
            (QPalette.ColorRole.Button, "secondary"), (QPalette.ColorRole.ButtonText, "text"),
            (QPalette.ColorRole.Highlight, "accent"), (QPalette.ColorRole.HighlightedText, "on_accent"),
            (QPalette.ColorRole.Light, "border"), (QPalette.ColorRole.Mid, "border"),
            (QPalette.ColorRole.PlaceholderText, "muted"),
        ):
            palette.setColor(role, QColor(c[token]))
        self.setPalette(palette)
        self.setStyleSheet(f"""
            QWidget {{ color: {c['text']}; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; }}
            QMainWindow, QMainWindow > QWidget {{ background: {c['background']}; }}
            QLabel {{ background: transparent; }}
            QLabel#appTitle {{ font-size: 16px; font-weight: 600; }}
            QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
            QLabel#serviceStatus {{ color: {c['muted']}; padding-right: 6px; font-size: 12px; }}
            QLabel#serviceStatus[state="running"] {{ color: {c['success']}; }}
            QLabel#serviceStatus[state="stop_failed"] {{ color: {c['error']}; }}
            QLabel#serviceStatus[state="starting"], QLabel#serviceStatus[state="compiling"], QLabel#serviceStatus[state="stopping"] {{ color: {c['warning']}; }}
            QLabel#portFeedback {{ padding: 8px 20px; border-bottom: 1px solid {c['border']}; }}
            QLabel[level="error"] {{ color: {c['error']}; }}
            QLabel[level="warning"] {{ color: {c['warning']}; }}
            QLabel[level="success"] {{ color: {c['success']}; }}
            QFrame#topBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
            QPushButton#textLink, QPushButton#searchOption {{ color: {c['muted']}; background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px 10px; }}
            QPushButton#textLink {{ color: {c['accent']}; }}
            QPushButton#searchOption {{ padding: 0; font-family: 'Consolas'; font-size: 14px; }}
            QPushButton#textLink:hover, QPushButton#searchOption:hover {{ background: {c['secondary']}; }}
            QPushButton#searchOption:checked {{ color: {c['accent']}; background: {c['selected']}; border-color: {c['border']}; }}
            QPushButton:focus {{ border: 1px solid {c['accent']}; }}
            QLabel#searchFeedback {{ color: {c['error']}; padding: 6px 20px; }}
            QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 0 9px; }}
            QToolButton[iconOnly="true"] {{ padding: 0; }}
            QToolButton:hover {{ background: {c['secondary']}; }}
            QToolButton:pressed, QToolButton:checked {{ color: {c['accent']}; background: {c['selected']}; border-color: {c['border']}; }}
            QToolButton#primary {{ color: {c['on_accent']}; background: {c['accent']}; border-color: {c['accent']}; font-weight: 600; }}
            QToolButton#primary:hover {{ background: {c['accent_hover']}; }}
            QToolButton:disabled {{ color: {c['disabled']}; }}
            QToolButton#primary:disabled {{ color: {c['disabled']}; background: {c['secondary']}; border-color: {c['border']}; }}
            QToolButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
            QLineEdit, QComboBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 7px 10px; selection-background-color: {c['selected']}; selection-color: {c['text']}; }}
            QLineEdit:disabled {{ color: {c['disabled']}; background: {c['secondary']}; }}
            QComboBox {{ padding-right: 12px; min-width: 80px; }}
            QComboBox QAbstractItemView {{ background: {c['raised']}; selection-background-color: {c['selected']}; color: {c['text']}; border: 1px solid {c['border']}; }}
            QTabWidget::pane {{ border: 0; border-top: 1px solid {c['border']}; background: {c['surface']}; }}
            QWidget#servicePanel {{ background: {c['surface']}; }}
            QTabBar::tab {{ color: {c['muted']}; padding: 11px 20px; border-bottom: 2px solid transparent; }}
            QTabBar::tab:selected {{ color: {c['accent']}; border-bottom-color: {c['accent']}; font-weight: 600; }}
            QTabBar::tab:hover {{ background: {c['secondary']}; }}
            QTabBar::tab:focus {{ background: {c['selected']}; }}
            QFrame#logToolbar {{ border-bottom: 1px solid {c['border']}; }}
            QPlainTextEdit#logView {{ background: {c['surface']}; color: {c['text']}; border: 0; padding: 14px 20px; font-family: 'Consolas', 'Microsoft YaHei UI'; font-size: 13px; selection-background-color: {c['selected']}; selection-color: {c['text']}; }}
            QLabel#logStatus {{ color: {c['muted']}; background: {c['background']}; border-top: 1px solid {c['border']}; padding: 6px 20px; font-size: 12px; }}
            QScrollBar:vertical {{ background: {c['surface']}; width: 9px; margin: 0; }}
            QScrollBar:horizontal {{ background: {c['surface']}; height: 9px; margin: 0; }}
            QScrollBar::handle {{ background: {c['border']}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
            QScrollBar::handle:hover {{ background: {c['muted']}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
            QToolTip {{ color: {c['text']}; background: {c['raised']}; border: 1px solid {c['border']}; padding: 5px 8px; }}
        """)
        for button in self.findChildren(IconButton):
            button.set_theme(c)
        for service in (self.backend, self.frontend):
            service.highlighter.colors = c
            service.highlighter.rehighlight()

    def _on_frontend_mode_change(self, mode: str, *, announce: bool = True) -> None:
        cmd = [
            self.npm_cmd, "run", "start" if mode == "生产模式" else "dev",
            "--", "--hostname", "127.0.0.1", "--port", str(self.frontend_port),
        ]

        self.frontend.set_command(cmd, build_before_start=mode == "生产模式")
        if announce and self.frontend.is_running():
            self.frontend.write_log("[INFO] 前端运行模式已切换，重启前端后生效。\n")

    def _build_backend_command(self) -> list[str]:
        return [
            str(VENV_PYTHON), "main.py",
            "--debug" if self._backend_debug_enabled else "--no-debug",
        ]

    def _on_backend_debug_change(self) -> None:
        enabled = self.backend_debug.isChecked()
        if self.backend.is_stopped():
            self._backend_debug_enabled = enabled
            self.backend.set_command(self._build_backend_command())
            return
        if self.backend.get_state() != "running" or self._backend_debug_reply is not None:
            self.backend_debug.blockSignals(True)
            self.backend_debug.setChecked(self._backend_debug_enabled)
            self.backend_debug.blockSignals(False)
            return
        request = QNetworkRequest(QUrl(f"http://127.0.0.1:{self.backend_port}/api/runtime/logging"))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setTransferTimeout(3000)
        self.backend_debug.setEnabled(False)
        reply = self._network.put(request, json.dumps({"debug": enabled}).encode("utf-8"))
        self._backend_debug_reply = reply
        proc = self.backend._proc
        reply.finished.connect(lambda: self._finish_backend_debug_change(reply, enabled, proc))

    def _finish_backend_debug_change(self, reply: QNetworkReply, enabled: bool, proc: subprocess.Popen) -> None:
        try:
            if self._closing:
                return
            if proc is not self.backend._proc or self.backend.get_state() != "running":
                raise ValueError("后端已停止或重新启动，请在运行后重试")
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            response = json.loads(bytes(reply.readAll()))
            if response["debug"] is not enabled:
                raise ValueError("后端返回的调试日志状态与请求不一致")
            self._backend_debug_enabled = enabled
            self.backend.write_log(f"[INFO] 调试日志已{'开启' if enabled else '关闭'}，立即生效。\n")
        except (ValueError, KeyError, TypeError) as exc:
            self.backend.write_log(f"[ERROR] 调试日志切换失败：{exc}\n")
        finally:
            self.backend_debug.blockSignals(True)
            self.backend_debug.setChecked(self._backend_debug_enabled)
            self.backend_debug.blockSignals(False)
            self.backend.set_command(self._build_backend_command())
            self._backend_debug_reply = None
            reply.deleteLater()
            self._sync_port_controls()

    def _prepare_startup(self, targets: tuple) -> None:
        """后台检查成功后才启动指定服务，检查期间窗口仍可操作和关闭。

        Args: targets: 待启动的服务面板及显示名称。
        Returns: 无，结果交给现有 Qt 定时器处理。
        """
        if self._preflight_active or self._closing:
            return
        if not self.backend.is_stopped():
            for service, label in targets:
                if self._service_can_start(service, label): service.start()
            return
        self._preflight_active = True
        self._preflight_cancelled.clear()
        self._preflight_targets = targets
        self._set_port_status("正在检查用户文件…")
        self._sync_port_controls()
        env = self.backend._build_env()
        self._preflight_thread = threading.Thread(target=self._run_preflight, args=(env,), daemon=True)
        self._preflight_thread.start()

    def _run_preflight(self, env: dict[str, str]) -> None:
        messages = []
        try:
            kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
            proc = subprocess.Popen(
                [str(VENV_PYTHON), "-u", "-m", "backend.migrations"], cwd=BASE_DIR, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", **kwargs,
            )
            with self._preflight_lock:
                self._preflight_proc = proc
                if self._preflight_cancelled.is_set(): self.backend._kill_proc(proc)
            with proc.stdout:
                for line in proc.stdout:
                    message = line.strip()
                    if message.startswith("[stage] "):
                        self._preflight_events.append(("progress", message[8:]))
                    elif message:
                        messages.append(message)
            code = proc.wait()
            self._preflight_events.append(("finished", (code, "；".join(messages))))
        except (OSError, UnicodeError):
            self._preflight_events.append(("finished", (1, "无法运行启动检查，请检查 Python 环境和文件权限。")))

    def _poll_preflight(self) -> None:
        # 后台线程只登记结果；所有控件更新和服务启动都留在 Qt 线程。
        while self._preflight_events:
            event, result = self._preflight_events.popleft()
            if event == "progress":
                if not self._closing: self._set_port_status(result)
                continue
            self._preflight_active = False
            targets, self._preflight_targets = self._preflight_targets, ()
            if self._closing or self._preflight_cancelled.is_set(): continue
            code, message = result
            if code not in (0, 2):
                self._set_port_status(message or "启动检查失败，请检查 user_data/migrations。", "error")
                continue
            self._set_port_status(message or "启动检查完成。", "warning" if code == 2 else "success")
            if all(self._service_can_start(service, label) for service, label in targets):
                for service, _ in targets: service.start()

    def _toggle_service(self, service: ServicePanel, label: str) -> None:
        if self._preflight_active or self._closing: return
        if service.get_state() in {"starting", "compiling", "running", "stop_failed"}:
            service.stop()
        elif service.is_stopped() and self._ensure_port_settings_applied():
            if service is self.frontend and not self._service_can_start(self.backend, "后端"):
                return
            if self._service_can_start(service, label):
                self._prepare_startup(((service, label),))
        self._sync_port_controls()

    def _toggle_all(self) -> None:
        states = (self.backend.get_state(), self.frontend.get_state())
        if "stopping" in states:
            return
        if any(state in {"starting", "compiling", "running", "stop_failed"} for state in states):
            self.stop_all()
        else:
            self.start_all()
        self._sync_port_controls()

    def start_all(self) -> None:
        """检查端口后在后台预检，通过后启动前后端。"""
        if self._preflight_active or self._closing: return
        if not self._ensure_port_settings_applied():
            return
        if not self._service_can_start(self.backend, "后端"):
            return
        if not self._service_can_start(self.frontend, "前端"):
            return
        self._prepare_startup(((self.backend, "后端"), (self.frontend, "前端")))

    def stop_all(self) -> None:
        """停止本窗口启动的前后端。"""
        self.backend.stop()
        self.frontend.stop()

    def closeEvent(self, event) -> None:
        """先在后台收尾本窗口启动的进程，再关闭窗口。

        Args:
            event: Qt 窗口关闭事件。

        Returns:
            无。
        """
        if self._cleanup_done.is_set():
            self.backend.timer.stop()
            self.frontend.timer.stop()
            self.control_timer.stop()
            atexit.unregister(self._atexit_cleanup)
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self._cleanup_finished.clear()
            self._cleanup_error = None
            self.centralWidget().setEnabled(False)
            self._set_port_status("正在停止服务并保存日志…")
            threading.Thread(target=self._atexit_cleanup, daemon=True).start()

    def _atexit_cleanup(self) -> None:
        if not self._cleanup_lock.acquire(blocking=False):
            return
        failures = []
        try:
            self._preflight_cancelled.set()
            with self._preflight_lock:
                preflight_proc = self._preflight_proc
                if preflight_proc is not None and not self.backend._kill_proc(preflight_proc):
                    failures.append("启动检查进程未能停止")
            if self._preflight_thread is not None:
                self._preflight_thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
                if self._preflight_thread.is_alive(): failures.append("启动检查尚未结束")
            for service in (self.backend, self.frontend):
                try:
                    if not service.force_cleanup():
                        failures.append(service._stop_error or "服务尚未停止")
                except Exception as exc:
                    service._report_stop_failure(str(exc))
                    failures.append(str(exc))
            self._cleanup_error = "；".join(failures) or None
            if not failures:
                self._cleanup_done.set()
        finally:
            self._cleanup_finished.set()
            self._cleanup_lock.release()


def main() -> None:
    """打开桌面启动器，并在窗口关闭后退出进程。

    Args:
        无。

    Returns:
        无。
    """
    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    try:
        notices = prepare_files()
    except Exception as exc:
        message = str(exc) if isinstance(exc, MigrationError) else "启动检查失败，请检查文件权限及迁移记录，原数据和备份已保留。"
        QMessageBox.critical(None, "无法启动", message)
        return
    window = App()
    if notices:
        window._set_port_status("；".join(notices), "warning")
    window.show()
    sys.exit(qt_app.exec())
