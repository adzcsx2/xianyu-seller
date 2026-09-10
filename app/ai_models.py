"""Fetch model identifiers from an OpenAI-compatible model service."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import requests


def extract_model_ids(payload: Any) -> list[str]:
    """Extract unique model IDs from a standard OpenAI models response."""
    if not isinstance(payload, dict):
        return []

    raw_models = payload.get("data", [])
    if not isinstance(raw_models, list):
        return []

    model_ids = {
        item.get("id", "").strip()
        for item in raw_models
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return sorted(model_id for model_id in model_ids if model_id)


def fetch_available_models(
    base_url: str,
    api_key: str,
    *,
    timeout: int = 15,
    allow_private_hosts: bool = False,
) -> list[str]:
    """Fetch model IDs without exposing credentials in errors or return data."""
    normalized_base_url = validate_model_service_url(
        base_url,
        allow_private_hosts=allow_private_hosts,
    )

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = requests.get(
        f"{normalized_base_url}/models",
        headers=headers,
        timeout=timeout,
        allow_redirects=False,
    )
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and 300 <= status_code < 400:
        raise ValueError("模型服务地址不允许重定向")
    response.raise_for_status()
    return extract_model_ids(response.json())


def validate_model_service_url(
    base_url: str,
    *,
    allow_private_hosts: bool = False,
) -> str:
    """Validate an OpenAI-compatible URL before making a server-side request."""
    normalized_base_url = (base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise ValueError("未配置模型服务地址")

    parsed = urlsplit(normalized_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("模型服务地址必须使用 http 或 https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("模型服务地址包含不允许的 URL 部分")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("模型服务地址端口无效") from exc

    if allow_private_hosts:
        return normalized_base_url

    try:
        addresses = {
            ipaddress.ip_address(parsed.hostname).compressed,
        }
    except ValueError:
        try:
            addresses = {
                result[4][0]
                for result in socket.getaddrinfo(
                    parsed.hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise ValueError("模型服务地址无法解析") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("模型服务地址不允许指向内网或本机")

    return normalized_base_url
