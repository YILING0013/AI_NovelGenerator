import json

from ui.generation_handlers import _log_blueprint_runtime_telemetry


class _DummyUI:
    def __init__(self):
        self.logs = []

    def safe_log(self, message: str):
        self.logs.append(message)


def test_log_blueprint_runtime_telemetry_logs_retry_summary(tmp_path):
    state = {
        "target_chapters": 16,
        "last_generated_chapter": 3,
        "last_run_elapsed_seconds": 128.6,
        "last_batch_telemetry": {
            "chapter_range": "3-3",
            "status": "success",
            "attempt_count": 3,
            "success_attempt": 3,
            "total_seconds": 26.2,
            "retry_reasons": ["validation_failed", "rate_limited"],
        },
        "batch_telemetry_history": [
            {
                "chapter_range": "1-1",
                "status": "success",
                "attempt_count": 1,
                "retry_reasons": [],
            },
            {
                "chapter_range": "2-2",
                "status": "success",
                "attempt_count": 2,
                "retry_reasons": ["validation_failed"],
            },
            {
                "chapter_range": "3-3",
                "status": "success",
                "attempt_count": 3,
                "success_attempt": 3,
                "total_seconds": 26.2,
                "retry_reasons": ["validation_failed", "rate_limited"],
            },
        ],
    }
    (tmp_path / ".blueprint_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ui = _DummyUI()
    _log_blueprint_runtime_telemetry(ui, str(tmp_path), max_recent=3)

    combined = "\n".join(ui.logs)
    assert "Step2运行遥测" in combined
    assert "目录进度: 第3章 / 目标16章" in combined
    assert "最近批次: 第3-3章" in combined
    assert "尝试3次(第3次成功)" in combined
    assert "结构验证失败" in combined
    assert "限流/配额" in combined
    assert "高频重试原因" in combined


def test_log_blueprint_runtime_telemetry_silent_without_state(tmp_path):
    ui = _DummyUI()
    _log_blueprint_runtime_telemetry(ui, str(tmp_path))
    assert ui.logs == []


def test_log_blueprint_runtime_telemetry_renders_mapping_gap_label(tmp_path):
    state = {
        "target_chapters": 4000,
        "last_generated_chapter": 180,
        "last_run_elapsed_seconds": 12.3,
        "last_batch_telemetry": {
            "chapter_range": "181-181",
            "status": "failed",
            "attempt_count": 1,
            "total_seconds": 1.2,
            "retry_reasons": ["mapping_gap"],
        },
        "batch_telemetry_history": [
            {
                "chapter_range": "181-181",
                "status": "failed",
                "attempt_count": 1,
                "retry_reasons": ["mapping_gap"],
            }
        ],
    }
    (tmp_path / ".blueprint_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ui = _DummyUI()
    _log_blueprint_runtime_telemetry(ui, str(tmp_path), max_recent=3)

    combined = "\n".join(ui.logs)
    assert "架构映射缺失" in combined
