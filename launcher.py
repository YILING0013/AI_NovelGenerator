"""Novel Generator 启动器 - 修复控制台乱码版本"""

import atexit
import os
import sys
import signal
import socket
import subprocess
import threading
import webbrowser

import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")

BACKEND_PORT = 8000
FRONTEND_PORT = 3000

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_port(port: int) -> bool:
    """终止占用指定端口的进程 (Windows)。"""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                pid = parts[4]
                subprocess.run(
                    ["taskkill", "/PID", pid, "/T", "/F"],
                    check=False, capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return True
    except Exception:
        pass
    return False

class ServicePanel(ctk.CTkFrame):
    """单个服务的日志面板 + 控制按钮。"""

    def __init__(self, master, title: str, command: list[str], cwd: str,
                 port: int, url: str, env=None):
        super().__init__(master, corner_radius=10)
        self.command = command
        self.cwd = cwd
        self.env = env or {}
        self.port = port
        self.url = url
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=12, pady=(10, 0))

        ctk.CTkLabel(self.header, text=title, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        self.status_dot = ctk.CTkLabel(self.header, text="\u25cf", font=ctk.CTkFont(size=14),
                                       text_color="gray")
        self.status_dot.pack(side="left", padx=(8, 0))
        self.status_label = ctk.CTkLabel(self.header, text="已停止",
                                         font=ctk.CTkFont(size=12), text_color="gray")
        self.status_label.pack(side="left", padx=(4, 0))

        self.log = ctk.CTkTextbox(
            self, height=180, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=("#f5f5f5", "#1a1a1a"), text_color=("#1e1e1e", "#d4d4d4"),
            corner_radius=8, state="disabled", wrap="word",
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=12, pady=(8, 10))

        self.start_btn = ctk.CTkButton(
            btn_bar, text="启动", width=80, height=30,
            fg_color=("#4a9d5b", "#2d7a3a"), hover_color=("#3d8a4e", "#246830"),
            command=self.start,
        )
        self.start_btn.pack(side="left", padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            btn_bar, text="停止", width=80, height=30,
            fg_color=("#c0392b", "#a93226"), hover_color=("#a33025", "#8c2920"),
            command=self.stop, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = ctk.CTkButton(
            btn_bar, text="清空日志", width=80, height=30,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"), text_color=("gray30", "gray70"),
            hover_color=("gray85", "gray20"),
            command=self.clear_log,
        )
        self.clear_btn.pack(side="left", padx=(0, 6))

        self.open_btn = ctk.CTkButton(
            btn_bar, text="打开网页", width=80, height=30,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"), text_color=("gray30", "gray70"),
            hover_color=("gray85", "gray20"),
            command=lambda: webbrowser.open(self.url),
        )
        self.open_btn.pack(side="right")

    def _append(self, text: str):
        should_autoscroll = self._should_autoscroll()
        self.log.configure(state="normal")
        self.log.insert("end", text)
        if should_autoscroll:
            self.log.see("end")
        self.log.configure(state="disabled")

    def _should_autoscroll(self) -> bool:
        try:
            _, bottom = self.log.yview()
            return bottom >= 0.995
        except Exception:
            return True

    def _read_stream(self, stream):
        """以字节流读取并尝试多编码解码以防止乱码。"""
        try:
            # 使用字节流读取，而不是 text=True
            for line_bytes in iter(stream.readline, b""):
                if not line_bytes:
                    break
                
                # 尝试解码逻辑
                line_str = ""
                try:
                    line_str = line_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        # Windows 下系统消息通常是 GBK
                        line_str = line_bytes.decode("gbk", errors="replace")
                    except Exception:
                        line_str = line_bytes.decode("utf-8", errors="replace")
                
                self.log.after(0, self._append, line_str)
        except Exception as e:
            self.log.after(0, self._append, f"\n[Launcher Error] 读取流异常: {e}\n")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_status(self, running: bool):
        if running:
            self.status_dot.configure(text_color="#2ecc71")
            self.status_label.configure(text="运行中", text_color="#2ecc71")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
        else:
            self.status_dot.configure(text_color="gray")
            self.status_label.configure(text="已停止", text_color="gray")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

    def _monitor(self):
        t_out = threading.Thread(target=self._read_stream, args=(self._proc.stdout,), daemon=True)
        t_err = threading.Thread(target=self._read_stream, args=(self._proc.stderr,), daemon=True)
        t_out.start()
        t_err.start()

        self._proc.wait()
        t_out.join(timeout=1)
        t_err.join(timeout=1)

        code = self._proc.returncode
        self.log.after(0, self._append, f"\n--- 进程退出 (code {code}) ---\n")
        self.log.after(0, lambda: self._on_stopped())

    def _on_stopped(self):
        self._proc = None
        self._set_status(False)

    def start(self):
        if self._proc is not None and self._proc.poll() is None:
            return

        # 端口冲突检查
        if is_port_in_use(self.port):
            self._append(f"[WARN] 端口 {self.port} 已被占用，正在终止残留进程...\n")
            kill_port(self.port)
            import time
            for _ in range(10):
                time.sleep(0.3)
                if not is_port_in_use(self.port):
                    break
            if is_port_in_use(self.port):
                self._append(f"[ERROR] 无法释放端口 {self.port}\n")
                return
            self._append(f"[INFO] 端口 {self.port} 已释放\n")

        self._append(f"> {' '.join(self.command)}\n")

        # 环境变量增强：强制子进程使用 UTF-8 环境
        full_env = os.environ.copy()
        full_env.update(self.env)
        full_env["PYTHONIOENCODING"] = "utf-8"
        full_env["PYTHONUTF8"] = "1"
        full_env["NODE_OPTIONS"] = "--input-type=module" # 针对 Node 的一些配置，可选

        kwargs = {
            "cwd": self.cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": False,  # 关键：改为 False，手动处理字节流解码
            "env": full_env,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )

        try:
            self._proc = subprocess.Popen(self.command, **kwargs)
            self._set_status(True)
            self._thread = threading.Thread(target=self._monitor, daemon=True)
            self._thread.start()
        except Exception as e:
            self._append(f"[ERROR] 启动进程失败: {e}\n")

    def stop(self):
        if self._proc is None:
            return
        self._kill_proc()

    def _kill_proc(self):
        """强制终止子进程树。"""
        if self._proc is None or self._proc.poll() is not None:
            return
        pid = self._proc.pid
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False, capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass

    def force_cleanup(self):
        """退出时的同步清理，不更新 UI。"""
        self._kill_proc()

    def set_command(self, command: list[str]):
        """动态修改启动命令"""
        self.command = command

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Novel Generator Launcher")
        self.geometry("820x760")
        self.minsize(640, 600)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.pack(fill="x", padx=16, pady=(14, 0))

        ctk.CTkLabel(
            title_frame, text="Novel Generator",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left")

        self.theme_btn = ctk.CTkButton(
            title_frame, text="主题切换", width=80, height=28,
            fg_color="transparent", border_width=1,
            border_color=("gray70", "gray30"), text_color=("gray30", "gray70"),
            hover_color=("gray85", "gray20"),
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="right")

        self.npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

        self.backend = ServicePanel(
            self, title="Backend  /  FastAPI",
            command=[VENV_PYTHON, "main.py"],
            cwd=BASE_DIR, port=BACKEND_PORT,
            url=f"http://localhost:{BACKEND_PORT}/docs",
        )
        self.backend.pack(fill="both", expand=True, padx=12, pady=(10, 4))

        self.backend_debug = ctk.CTkCheckBox(
            self.backend.header,
            text="后端调试日志",
            command=self._on_backend_debug_change,
        )
        self.backend_debug.pack(side="right", padx=(0, 10))
        self._on_backend_debug_change()

        self.frontend = ServicePanel(
            self, title="Frontend  /  Next.js",
            command=[],
            cwd=FRONTEND_DIR, port=FRONTEND_PORT,
            url=f"http://localhost:{FRONTEND_PORT}",
        )
        self.frontend.pack(fill="both", expand=True, padx=12, pady=(4, 4))

        self.frontend_mode = ctk.CTkSegmentedButton(
            self.frontend.header,
            values=["生产模式", "开发模式"],
            command=self._on_frontend_mode_change
        )
        self.frontend_mode.pack(side="right", padx=(0, 10))
        self.frontend_mode.set("生产模式")
        self._on_frontend_mode_change("生产模式")

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=(4, 12))

        ctk.CTkButton(
            bottom, text="全部启动", width=120, height=34,
            fg_color=("#4a9d5b", "#2d7a3a"), hover_color=("#3d8a4e", "#246830"),
            command=self.start_all,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bottom, text="全部停止", width=120, height=34,
            fg_color=("#c0392b", "#a93226"), hover_color=("#a33025", "#8c2920"),
            command=self.stop_all,
        ).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        atexit.register(self._atexit_cleanup)

    def _toggle_theme(self):
        current = ctk.get_appearance_mode()
        ctk.set_appearance_mode("light" if current == "Dark" else "dark")

    def _on_frontend_mode_change(self, mode: str):
        if mode == "生产模式":
            if sys.platform == "win32":
                cmd = ["cmd.exe", "/c", f"{self.npm_cmd} run build && {self.npm_cmd} run start"]
            else:
                cmd = ["sh", "-c", f"{self.npm_cmd} run build && {self.npm_cmd} run start"]
        else:
            cmd = [self.npm_cmd, "run", "dev"]
        self.frontend.set_command(cmd)

    def _build_backend_command(self) -> list[str]:
        cmd = [VENV_PYTHON, "main.py"]
        if self.backend_debug.get():
            cmd.append("--debug")
        return cmd

    def _on_backend_debug_change(self):
        self.backend.set_command(self._build_backend_command())
        if self.backend._proc is not None and self.backend._proc.poll() is None:
            self.backend._append("[INFO] 后端调试模式已切换，重启后端后生效。\n")

    def start_all(self):
        self.backend.start()
        self.frontend.start()

    def stop_all(self):
        self.backend.stop()
        self.frontend.stop()

    def _on_close(self):
        self.backend.force_cleanup()
        self.frontend.force_cleanup()
        self.destroy()

    def _atexit_cleanup(self):
        self.backend.force_cleanup()
        self.frontend.force_cleanup()


if __name__ == "__main__":
    App().mainloop()