# -*- coding: utf-8 -*-
"""Proxy utility tests."""

import os

from ui.proxy_utils import build_proxy_url, apply_proxy_env, clear_proxy_env, PROXY_ENV_KEYS


def test_build_proxy_url_with_plain_host_and_port():
    assert build_proxy_url("127.0.0.1", "1080") == "http://127.0.0.1:1080"


def test_build_proxy_url_normalizes_socks_scheme():
    assert build_proxy_url("socks://localhost", "1080") == "socks5://localhost:1080"


def test_build_proxy_url_keeps_existing_scheme_and_port():
    assert build_proxy_url("http://example.com:8080", "") == "http://example.com:8080"


def test_apply_and_clear_proxy_env():
    proxy_url = "http://127.0.0.1:8888"
    apply_proxy_env(proxy_url)

    for key in PROXY_ENV_KEYS:
        assert os.environ.get(key) == proxy_url

    clear_proxy_env()

    for key in PROXY_ENV_KEYS:
        assert key not in os.environ

