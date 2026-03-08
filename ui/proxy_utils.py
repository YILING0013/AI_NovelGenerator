# ui/proxy_utils.py
# -*- coding: utf-8 -*-
"""Proxy environment helpers shared by GUI modules."""

from __future__ import annotations

import os

PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def build_proxy_url(address: str, port: str) -> str:
    """Build normalized proxy URL from address + optional port."""
    address = (address or "").strip()
    port = (port or "").strip()
    if not address:
        return ""

    if "://" in address:
        scheme, rest = address.split("://", 1)
        scheme = scheme.lower().strip()
        if scheme == "socks":
            scheme = "socks5"
        rest = rest.strip().rstrip("/")
        if port and not rest.rsplit(":", 1)[-1].isdigit():
            rest = f"{rest}:{port}"
        return f"{scheme}://{rest}"

    if port and not address.rsplit(":", 1)[-1].isdigit():
        address = f"{address}:{port}"
    return f"http://{address}"


def clear_proxy_env() -> None:
    """Clear all proxy environment variables."""
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def apply_proxy_env(proxy_url: str) -> None:
    """Set all proxy environment variables to the same URL."""
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    os.environ["ALL_PROXY"] = proxy_url
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url
    os.environ["all_proxy"] = proxy_url

