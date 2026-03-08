# main.py
# -*- coding: utf-8 -*-
import warnings
import os
import subprocess
import customtkinter as ctk

# 过滤pkg_resources弃用警告
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="pkg_resources is deprecated as an API",
    module="jieba._compat"
)

from ui import NovelGeneratorGUI


def _read_scale_env(name: str):
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        scale = float(value)
    except ValueError:
        return None
    if scale <= 0:
        return None
    return scale


def _detect_gui_scale(app) -> float:
    explicit_scale = _read_scale_env("GUI_SCALE")
    if explicit_scale:
        return explicit_scale

    gdk_scale = _read_scale_env("GDK_SCALE")
    if gdk_scale:
        return gdk_scale

    gdk_dpi_scale = _read_scale_env("GDK_DPI_SCALE")
    if gdk_dpi_scale:
        return gdk_dpi_scale

    xft_scale = _read_xft_dpi_scale()
    if xft_scale:
        return xft_scale

    try:
        tk_scaling = float(app.tk.call("tk", "scaling"))
        baseline_scaling = 96.0 / 72.0
        if tk_scaling > 0:
            return tk_scaling / baseline_scaling
    except Exception:
        pass

    return 1.0


def _read_xft_dpi_scale():
    try:
        result = subprocess.run(
            ["xrdb", "-query"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except Exception:
        return None

    if result.returncode != 0 or not result.stdout:
        return None

    for line in result.stdout.splitlines():
        if not line.lower().startswith("xft.dpi"):
            continue
        _, _, value = line.partition(":")
        value = value.strip()
        try:
            dpi = float(value)
        except ValueError:
            return None
        if dpi <= 0:
            return None
        return dpi / 96.0

    return None


def _apply_gui_scale(app):
    scale = _detect_gui_scale(app)
    scale = max(0.8, min(scale, 3.0))
    app.tk.call("tk", "scaling", scale * (96.0 / 72.0))
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)

def main():
    # 创建并启动GUI
    app = ctk.CTk()
    _apply_gui_scale(app)
    gui = NovelGeneratorGUI(app)
    app.mainloop()

if __name__ == "__main__":
    main()
