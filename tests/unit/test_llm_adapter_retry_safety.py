from __future__ import annotations

import logging

from llm_adapters import ZhipuAdapter, with_intelligent_retry


def test_with_intelligent_retry_retries_500_with_backoff(monkeypatch) -> None:
    sleeps: list[float] = []
    attempts = {"count": 0}

    monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(float(seconds)))
    monkeypatch.setattr("random.uniform", lambda _a, _b: 0.0)

    @with_intelligent_retry(max_attempts=3)
    def _call() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("500 Internal Server Error")
        return "ok"

    assert _call() == "ok"
    assert attempts["count"] == 3
    # 服务端5xx错误会触发加倍等待：第1次约2s，第2次约4s
    assert sleeps[:2] == [2.0, 4.0]


def test_zhipu_error_log_does_not_expose_api_key_prefix(monkeypatch, caplog) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr("random.uniform", lambda _a, _b: 0.0)

    adapter = ZhipuAdapter(
        api_key="sk-very-secret-key",
        base_url="https://open.bigmodel.cn/api/anthropic/v1/messages",
        model_name="glm-5",
        max_tokens=32,
        temperature=0.1,
        timeout=1,
    )

    def _raise_server_error(_prompt: str) -> str:
        raise RuntimeError("500 Internal Server Error")

    monkeypatch.setattr(adapter, "_invoke_anthropic_api", _raise_server_error)

    caplog.set_level(logging.ERROR)
    result = adapter.invoke("test-prompt")

    assert result == ""
    assert "api_key前缀" not in caplog.text
    assert "key_length" in caplog.text
    assert "sk-very" not in caplog.text
