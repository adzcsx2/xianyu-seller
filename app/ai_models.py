"""Fetch model identifiers from an OpenAI-compatible model service."""

from __future__ import annotations

from typing import Any

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
) -> list[str]:
    """Fetch model IDs without exposing credentials in errors or return data."""
    normalized_base_url = (base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise ValueError("未配置模型服务地址")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = requests.get(
        f"{normalized_base_url}/models",
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return extract_model_ids(response.json())
