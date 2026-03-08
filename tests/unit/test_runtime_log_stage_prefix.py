# -*- coding: utf-8 -*-
"""Tests for runtime stage prefix injection on root logs."""

import logging

from novel_generator.common import (
    RuntimeStagePrefixFilter,
    clear_runtime_log_stage,
    set_runtime_log_stage,
)


def _build_record(message: str, args: tuple = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="root",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
    )


def test_runtime_stage_prefix_filter_adds_stage_prefix() -> None:
    stage_filter = RuntimeStagePrefixFilter()
    set_runtime_log_stage("S2")
    try:
        record = _build_record("hello %s", ("world",))
        assert stage_filter.filter(record) is True
        assert record.msg == "[S2] hello world"
        assert record.args == ()
    finally:
        clear_runtime_log_stage()


def test_runtime_stage_prefix_filter_does_not_duplicate_existing_prefix() -> None:
    stage_filter = RuntimeStagePrefixFilter()
    set_runtime_log_stage("S2")
    try:
        record = _build_record("[S2] already prefixed")
        assert stage_filter.filter(record) is True
        assert record.msg == "[S2] already prefixed"
    finally:
        clear_runtime_log_stage()


def test_runtime_stage_prefix_filter_skips_when_stage_missing() -> None:
    stage_filter = RuntimeStagePrefixFilter()
    clear_runtime_log_stage()
    record = _build_record("plain-log")
    assert stage_filter.filter(record) is True
    assert record.msg == "plain-log"
