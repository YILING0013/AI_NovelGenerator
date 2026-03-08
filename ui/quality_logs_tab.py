# ui/quality_logs_tab.py
# -*- coding: utf-8 -*-
import os
import time
import customtkinter as ctk
from tkinter import messagebox

from ui.context_menu import TextWidgetContextMenu


def build_quality_logs_tab(self):
    """质量评分日志面板：展示每轮 raw/critic/final 分数与触发原因。"""
    self.quality_logs_tab = self.tabview.add("评分日志")
    self.quality_logs_tab.rowconfigure(5, weight=1)
    self.quality_logs_tab.columnconfigure(0, weight=1)

    title = ctk.CTkLabel(
        self.quality_logs_tab,
        text="质量闭环评分日志（raw/critic/loop_final；最终放行分见主日志）",
        font=("Microsoft YaHei", 12),
    )
    title.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")

    precheck_label = ctk.CTkLabel(
        self.quality_logs_tab,
        text="批量预检风险面板（红黄绿）",
        font=("Microsoft YaHei", 12),
    )
    precheck_label.grid(row=1, column=0, padx=8, pady=(4, 2), sticky="w")

    self.precheck_risk_text = ctk.CTkTextbox(
        self.quality_logs_tab,
        height=110,
        wrap="word",
        font=("Consolas", 11),
    )
    TextWidgetContextMenu(self.precheck_risk_text)
    self.precheck_risk_text.grid(row=2, column=0, padx=8, pady=(0, 4), sticky="ew")
    self.precheck_risk_text.insert("0.0", "暂无预检风险数据")
    self.precheck_risk_text.configure(state="disabled")

    stats_label = ctk.CTkLabel(
        self.quality_logs_tab,
        text="触发原因统计（实时）",
        font=("Microsoft YaHei", 12),
    )
    stats_label.grid(row=3, column=0, padx=8, pady=(4, 2), sticky="w")

    self.quality_reason_stats_text = ctk.CTkTextbox(
        self.quality_logs_tab,
        height=90,
        wrap="word",
        font=("Consolas", 11),
    )
    TextWidgetContextMenu(self.quality_reason_stats_text)
    self.quality_reason_stats_text.grid(row=4, column=0, padx=8, pady=(0, 4), sticky="ew")
    self.quality_reason_stats_text.insert("0.0", "暂无统计数据")
    self.quality_reason_stats_text.configure(state="disabled")

    self.quality_log_text = ctk.CTkTextbox(
        self.quality_logs_tab,
        wrap="word",
        font=("Consolas", 11),
    )
    TextWidgetContextMenu(self.quality_log_text)
    self.quality_log_text.grid(row=5, column=0, padx=8, pady=4, sticky="nsew")
    self.quality_log_text.configure(state="disabled")

    btn_frame = ctk.CTkFrame(self.quality_logs_tab, fg_color="transparent")
    btn_frame.grid(row=6, column=0, padx=8, pady=(4, 8), sticky="w")

    clear_btn = ctk.CTkButton(
        btn_frame,
        text="清空评分日志",
        width=120,
        font=("Microsoft YaHei", 12),
        command=lambda: _clear_quality_logs(self),
    )
    clear_btn.pack(side="left", padx=(0, 8))

    clear_precheck_btn = ctk.CTkButton(
        btn_frame,
        text="清空预检面板",
        width=120,
        font=("Microsoft YaHei", 12),
        command=lambda: _clear_precheck_risk(self),
    )
    clear_precheck_btn.pack(side="left", padx=(0, 8))

    export_precheck_btn = ctk.CTkButton(
        btn_frame,
        text="导出预检报告",
        width=120,
        font=("Microsoft YaHei", 12),
        command=lambda: _export_precheck_risk_markdown(self),
    )
    export_precheck_btn.pack(side="left", padx=(0, 8))


def _clear_quality_logs(self):
    if not hasattr(self, "quality_log_text"):
        return
    if hasattr(self, "_quality_event_keys"):
        self._quality_event_keys.clear()
    if hasattr(self, "_quality_reason_counts"):
        self._quality_reason_counts.clear()
    self.quality_log_text.configure(state="normal")
    self.quality_log_text.delete("0.0", "end")
    self.quality_log_text.configure(state="disabled")
    if hasattr(self, "quality_reason_stats_text"):
        self.quality_reason_stats_text.configure(state="normal")
        self.quality_reason_stats_text.delete("0.0", "end")
        self.quality_reason_stats_text.insert("0.0", "暂无统计数据")
        self.quality_reason_stats_text.configure(state="disabled")


def _clear_precheck_risk(self):
    if hasattr(self, "_precheck_risk_history"):
        self._precheck_risk_history.clear()
    if hasattr(self, "precheck_risk_text"):
        self.precheck_risk_text.configure(state="normal")
        self.precheck_risk_text.delete("0.0", "end")
        self.precheck_risk_text.insert("0.0", "暂无预检风险数据")
        self.precheck_risk_text.configure(state="disabled")


def _safe_project_dir(self) -> str:
    filepath_var = getattr(self, "filepath_var", None)
    if filepath_var is not None:
        try:
            project_dir = str(filepath_var.get()).strip()
            if project_dir and os.path.isdir(project_dir):
                return project_dir
        except (RuntimeError, ValueError, TypeError, OSError):
            pass
    return os.getcwd()


def _build_precheck_risk_markdown(history: list[dict]) -> str:
    records = [item for item in history if isinstance(item, dict)]
    lines = [
        "# 批量预检风险报告",
        "",
        f"- 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 记录条数: {len(records)}",
        "",
    ]
    if not records:
        lines.extend(
            [
                "## 结论",
                "暂无预检风险数据。",
                "",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    latest = records[-1]
    latest_metrics = latest.get("metrics", {}) if isinstance(latest.get("metrics"), dict) else {}
    lines.extend(
        [
            "## 最新风险快照",
            f"- 风险等级: {latest.get('risk_label', '未知')}",
            f"- 扫描范围: {latest.get('chapter_range', '-')}",
            f"- 风险分值: {int(latest.get('risk_score', 0) or 0)}",
            (
                "- 关键指标: "
                f"占位符{int(latest_metrics.get('placeholder_count', 0) or 0)} | "
                f"结构异常章{int(latest_metrics.get('structure_chapters', 0) or 0)} | "
                f"重复对{int(latest_metrics.get('duplicate_pairs', 0) or 0)} | "
                f"一致性提示章{int(latest_metrics.get('consistency_chapters', 0) or 0)} | "
                f"警告{int(latest_metrics.get('warnings_count', 0) or 0)}"
            ),
            "",
            "## 最近记录（最多20条）",
        ]
    )

    for item in records[-20:]:
        metrics = item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {}
        warnings = item.get("warnings", []) if isinstance(item.get("warnings"), list) else []
        lines.extend(
            [
                (
                    f"- [{item.get('timestamp', '-')}] "
                    f"{item.get('risk_label', '未知')} | "
                    f"范围 {item.get('chapter_range', '-')} | "
                    f"score={int(item.get('risk_score', 0) or 0)}"
                ),
                (
                    "  - 指标: "
                    f"占位符{int(metrics.get('placeholder_count', 0) or 0)} | "
                    f"结构异常章{int(metrics.get('structure_chapters', 0) or 0)} | "
                    f"重复对{int(metrics.get('duplicate_pairs', 0) or 0)} | "
                    f"一致性提示章{int(metrics.get('consistency_chapters', 0) or 0)} | "
                    f"警告{int(metrics.get('warnings_count', 0) or 0)}"
                ),
            ]
        )
        if warnings:
            for warning in warnings[:3]:
                lines.append(f"  - 告警: {warning}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _export_precheck_risk_markdown(self):
    history = getattr(self, "_precheck_risk_history", [])
    if not isinstance(history, list):
        history = []
    output_dir = _safe_project_dir(self)
    filename = f"batch_precheck_risk_report_{time.strftime('%Y%m%d_%H%M%S')}.md"
    output_path = os.path.join(output_dir, filename)

    try:
        content = _build_precheck_risk_markdown(history)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        if hasattr(self, "safe_log"):
            self.safe_log(f"🧾 预检风险Markdown报告已导出: {output_path}")
        try:
            messagebox.showinfo("导出成功", f"预检风险报告已导出：\n{output_path}")
        except (RuntimeError, ValueError, TypeError):
            pass
    except (OSError, RuntimeError, ValueError, TypeError) as export_error:
        if hasattr(self, "safe_log"):
            self.safe_log(f"❌ 导出预检风险报告失败: {export_error}")
        try:
            messagebox.showerror("导出失败", f"预检风险报告导出失败：\n{export_error}")
        except (RuntimeError, ValueError, TypeError):
            pass
