# -*- coding: utf-8 -*-
"""BatchPreChecker deep scan range filtering tests."""

from novel_generator import batch_pre_checker as batch_pre_checker_module


def test_deep_scan_filters_results_to_requested_range(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_pre_checker_module, "ValidationContext", lambda _filepath: object())

    class _PlaceholderDetector:
        def __init__(self, _context):
            pass

        def scan_all_chapters(self):
            return {2: [("待定", "待定标记", 1)], 12: [("待定", "待定标记", 1)]}

    class _StructureValidator:
        def __init__(self, _context):
            pass

        def scan_all_chapters(self):
            return {
                3: {"completeness": 0.7, "missing": ["基础元信息"]},
                14: {"completeness": 0.6, "missing": ["张力与冲突"]},
            }

    class _DuplicateDetector:
        def __init__(self, _context):
            pass

        def scan_all_chapters(self):
            return [
                (2, 3, 0.8, []),   # 命中范围
                (9, 11, 0.9, []),  # 越界，不应计入
            ]

    class _ConsistencyValidator:
        def __init__(self, _context):
            pass

        def scan_all_chapters(self):
            return [
                (5, ["issue-in-range"]),
                (15, ["issue-out-range"]),
            ]

    monkeypatch.setattr(batch_pre_checker_module, "PlaceholderDetector", _PlaceholderDetector)
    monkeypatch.setattr(batch_pre_checker_module, "StructureValidator", _StructureValidator)
    monkeypatch.setattr(batch_pre_checker_module, "DuplicateDetector", _DuplicateDetector)
    monkeypatch.setattr(batch_pre_checker_module, "ConsistencyValidator", _ConsistencyValidator)

    checker = batch_pre_checker_module.BatchPreChecker(str(tmp_path))
    checker._run_deep_scan(start_chapter=1, end_chapter=10)

    deep = checker.report["deep_checks"]
    assert deep["placeholder"]["chapters_affected"] == 1
    assert deep["placeholder"]["count"] == 1
    assert deep["structure"]["chapters_affected"] == 1
    assert deep["duplicate"]["pairs_found"] == 1
    assert deep["consistency"]["chapters_affected"] == 1
