"""Resolve AI configuration from deployment environment and manual settings."""

from __future__ import annotations

import os
from typing import Any, Mapping


AI_ENV_KEYS = {
    "api_key": "API_KEY",
    "base_url": "MODEL_BASE_URL",
    "model_name": "MODEL_NAME",
}


def get_env_ai_config() -> dict[str, str]:
    """Read deployment-provided AI settings without logging their values."""
    return {
        field: (os.getenv(env_key) or "").strip()
        for field, env_key in AI_ENV_KEYS.items()
    }


def resolve_ai_config(
    *,
    api_key: str | None,
    base_url: str | None,
    model_name: str | None,
) -> dict[str, str]:
    """Use saved UI settings first, then deployment environment defaults."""
    manual = {
        "api_key": (api_key or "").strip(),
        "base_url": (base_url or "").strip(),
        "model_name": (model_name or "").strip(),
    }
    env_config = get_env_ai_config()
    return {
        field: manual[field] or env_config[field]
        for field in AI_ENV_KEYS
    }


def apply_env_ai_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Overlay environment AI settings for the admin settings response.

    The response is a copy so callers cannot accidentally mutate persisted
    settings. ``ai_env_overrides`` is metadata for the UI and contains only
    booleans, never the environment values themselves.
    """
    result = dict(settings)
    env_config = get_env_ai_config()
    overrides: dict[str, bool] = {}
    field_mapping = {
        "api_key": "ai_api_key",
        "base_url": "ai_api_url",
        "model_name": "ai_model",
    }
    for field, setting_key in field_mapping.items():
        if not str(result.get(setting_key) or '').strip() and env_config[field]:
            result[setting_key] = env_config[field]
            overrides[field] = True
    result["ai_env_overrides"] = overrides
    return result
