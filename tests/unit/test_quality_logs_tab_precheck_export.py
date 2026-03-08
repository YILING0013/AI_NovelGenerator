from __future__ import annotations

from pathlib import Path

import ui.quality_logs_tab as quality_logs_tab
from ui.quality_logs_tab import _build_precheck_risk_markdown, _export_precheck_risk_markdown


def test_build_precheck_risk_markdown_contains_latest_snapshot():
    markdown = _build_precheck_risk_markdown(
        [
            {
                "timestamp": "2026-03-04 10:00:00",
                "chapter_range": "1-20",
                "risk_label": "🟡 中风险",
                "risk_score": 28,
                "metrics": {
                    "placeholder_count": 0,
                    "structure_chapters": 1,
                    "duplicate_pairs": 1,
                    "consistency_chapters": 2,
                    "warnings_count": 2,
                },
                "warnings": ["重复风险"],
            },
            {
                "timestamp": "2026-03-04 10:12:00",
                "chapter_range": "21-40",
                "risk_label": "🔴 高风险",
                "risk_score": 95,
                "metrics": {
                    "placeholder_count": 2,
                    "structure_chapters": 0,
                    "duplicate_pairs": 0,
                    "consistency_chapters": 1,
                    "warnings_count": 1,
                },
                "warnings": ["占位符问题"],
            },
        ]
    )

    assert "# 批量预检风险报告" in markdown
    assert "## 最新风险快照" in markdown
    assert "🔴 高风险" in markdown
    assert "范围 21-40" in markdown
    assert "占位符2" in markdown


def test_export_precheck_risk_markdown_writes_file(tmp_path: Path, monkeypatch):
    class _Var:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self) -> str:
            return self._value

    class _DummyUI:
        def __init__(self) -> None:
            self.filepath_var = _Var(str(tmp_path))
            self._precheck_risk_history = [
                {
                    "timestamp": "2026-03-04 12:00:00",
                    "chapter_range": "1-5",
                    "risk_label": "🟢 低风险",
                    "risk_score": 8,
                    "metrics": {
                        "placeholder_count": 0,
                        "structure_chapters": 0,
                        "duplicate_pairs": 0,
                        "consistency_chapters": 0,
                        "warnings_count": 0,
                    },
                    "warnings": [],
                }
            ]
            self.logs: list[str] = []

        def safe_log(self, message: str) -> None:
            self.logs.append(message)

    def _fake_strftime(fmt: str) -> str:
        if fmt == "%Y%m%d_%H%M%S":
            return "20260304_120000"
        return "2026-03-04 12:00:00"

    info_calls: list[tuple[str, str]] = []
    error_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(quality_logs_tab.time, "strftime", _fake_strftime)
    monkeypatch.setattr(quality_logs_tab.messagebox, "showinfo", lambda title, msg: info_calls.append((title, msg)))
    monkeypatch.setattr(quality_logs_tab.messagebox, "showerror", lambda title, msg: error_calls.append((title, msg)))

    ui = _DummyUI()
    _export_precheck_risk_markdown(ui)

    output_path = tmp_path / "batch_precheck_risk_report_20260304_120000.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "🟢 低风险" in content
    assert any("预检风险Markdown报告已导出" in log for log in ui.logs)
    assert info_calls
    assert not error_calls
