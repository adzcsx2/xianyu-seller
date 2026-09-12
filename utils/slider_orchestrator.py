"""Strict orchestration for the reference project's slider verification flow.

The page can look successful while the platform still withholds the real
``x5sec`` ticket.  Every engine therefore passes through the same result
normalizer before callers are allowed to update account cookies.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

import requests


DEFAULT_SLIDER_ENGINE = "playwright"
DRISSIONPAGE_ENGINE = "drissionpage"
REMOTE_ENGINE = "remote"
_COOKIE_ATTRIBUTES = {"path", "domain", "expires", "max-age", "secure", "httponly", "samesite"}


@dataclass(frozen=True)
class SliderVerificationResult:
    success: bool
    cookies: Optional[Dict[str, Any]]
    engine: str
    x5_cookies: Dict[str, Any]
    message: str

    def as_legacy_tuple(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        return self.success, self.cookies


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _remote_config_from_env() -> Tuple[str, str]:
    return (
        os.environ.get("XY_SLIDER_REMOTE_URL", "").strip(),
        os.environ.get("XY_SLIDER_REMOTE_SECRET", "").strip(),
    )


def parse_cookie_string(cookie_text: Optional[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not cookie_text:
        return result
    normalized = str(cookie_text).replace("\ufeff", "").replace(", ", "; ")
    for part in normalized.split(";"):
        item = part.strip()
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        if name and name.lower() not in _COOKIE_ATTRIBUTES:
            result[name] = value.strip()
    return result


def extract_x5_cookies(cookies: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(cookies, Mapping):
        return {}
    return {
        str(name): value
        for name, value in cookies.items()
        if str(name or "").lower().startswith("x5") or "x5sec" in str(name or "").lower()
    }


def has_x5_cookie(cookies: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(cookies, Mapping):
        return False
    return any(
        str(name or "").lower() == "x5sec" and bool(value)
        for name, value in cookies.items()
    )


def validate_slider_result(
    success: bool,
    cookies: Optional[Union[Mapping[str, Any], str]],
    *,
    engine: Optional[str] = DEFAULT_SLIDER_ENGINE,
) -> SliderVerificationResult:
    """Require a real x5/x5sec ticket, not just a visual success signal."""
    normalized_engine = str(engine or DEFAULT_SLIDER_ENGINE).strip() or DEFAULT_SLIDER_ENGINE
    if isinstance(cookies, str):
        normalized_cookies: Optional[Dict[str, Any]] = parse_cookie_string(cookies)
    elif isinstance(cookies, Mapping):
        normalized_cookies = dict(cookies)
    else:
        normalized_cookies = None
    x5_cookies = extract_x5_cookies(normalized_cookies)

    if not success:
        return SliderVerificationResult(False, None, normalized_engine, {}, "滑块验证失败")
    if not normalized_cookies:
        return SliderVerificationResult(
            False, None, normalized_engine, {}, "滑块视觉通过但未返回 Cookie，平台可能未真正放行"
        )
    if not has_x5_cookie(normalized_cookies):
        return SliderVerificationResult(
            False,
            normalized_cookies,
            normalized_engine,
            {},
            "滑块视觉通过但未获取到 x5sec Cookie，判定为失败；常见原因是浏览器环境/IP 仍被风控拦截",
        )
    return SliderVerificationResult(
        True,
        normalized_cookies,
        normalized_engine,
        x5_cookies,
        "滑块验证成功并获取到 x5sec Cookie",
    )


def _call_remote_solve(
    url: str,
    *,
    user_id: str,
    remote_url: str,
    remote_secret: str,
    timeout: int = 60,
) -> SliderVerificationResult:
    try:
        response = requests.post(
            remote_url,
            json={
                "secret_key": remote_secret,
                "account_id": user_id,
                "url": url,
                "browser_timeout": timeout,
            },
            timeout=max(10, int(timeout or 60)),
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        data = data if isinstance(data, dict) else {}
        cookies = data.get("cookies") or data.get("x5_cookies") or data.get("cookie")
        result = validate_slider_result(
            bool(payload.get("success")) if isinstance(payload, dict) else False,
            cookies,
            engine=REMOTE_ENGINE,
        )
        if not result.success and isinstance(payload, dict) and payload.get("message"):
            return SliderVerificationResult(
                False, result.cookies, REMOTE_ENGINE, result.x5_cookies, str(payload["message"])
            )
        return result
    except Exception as exc:
        return SliderVerificationResult(False, None, REMOTE_ENGINE, {}, f"远程滑块服务不可用: {exc}")


def _run_drissionpage_fallback(
    url: str,
    *,
    user_id: str,
    existing_cookies_str: str = "",
    headless: bool = True,
    max_retries: int = 3,
    handler_factory: Optional[Callable[..., Any]] = None,
) -> SliderVerificationResult:
    try:
        if handler_factory is None:
            from utils.refresh_util import DrissionHandler
            handler_factory = DrissionHandler
        handler = handler_factory(
            max_retries=max_retries,
            is_headless=headless,
            maximize_window=not headless,
            show_mouse_trace=False,
        )
        raw_cookies = handler.get_cookies(
            url, existing_cookies_str=existing_cookies_str, cookie_id=user_id
        )
        return validate_slider_result(bool(raw_cookies), raw_cookies, engine=DRISSIONPAGE_ENGINE)
    except Exception as exc:
        return SliderVerificationResult(False, None, DRISSIONPAGE_ENGINE, {}, f"DrissionPage兜底引擎执行失败: {exc}")


def _invoke_sync(slider: Any, url: str, **kwargs: Any):
    method = getattr(slider, "run", None) or getattr(slider, "solve", None)
    if not callable(method):
        raise AttributeError("slider has neither run() nor solve()")
    result = method(url, **kwargs)
    if hasattr(result, "__await__"):
        raise TypeError("slider solver is async; use run_slider_async_* helpers")
    return result


async def _invoke_async(slider: Any, url: str, **kwargs: Any):
    method = getattr(slider, "async_run", None) or getattr(slider, "solve", None)
    if not callable(method):
        raise AttributeError("slider has neither async_run() nor solve()")
    result = method(url, **kwargs)
    return await result if hasattr(result, "__await__") else result


def run_slider_strict(slider: Any, url: str, *, engine: Optional[str] = DEFAULT_SLIDER_ENGINE, **kwargs: Any):
    success, cookies = _invoke_sync(slider, url, **kwargs)
    return validate_slider_result(success, cookies, engine=engine)


def run_slider_with_fallback(
    slider: Any,
    url: str,
    *,
    engine: Optional[str] = DEFAULT_SLIDER_ENGINE,
    fallback_enabled: Optional[bool] = None,
    remote_enabled: Optional[bool] = None,
    remote_config: Optional[Tuple[str, str]] = None,
    remote_timeout: int = 60,
    fallback_headless: Optional[bool] = None,
    fallback_max_retries: int = 3,
    handler_factory: Optional[Callable[..., Any]] = None,
    **kwargs: Any,
):
    user_id = str(getattr(slider, "user_id", None) or getattr(slider, "pure_user_id", None) or "unknown")
    use_remote = _env_bool("XY_SLIDER_REMOTE_ENABLED", False) if remote_enabled is None else bool(remote_enabled)
    remote_url, remote_secret = remote_config or _remote_config_from_env()
    if use_remote and remote_url and remote_secret:
        remote_result = _call_remote_solve(
            url, user_id=user_id, remote_url=remote_url, remote_secret=remote_secret, timeout=remote_timeout
        )
        if remote_result.success:
            return remote_result

    primary = run_slider_strict(slider, url, engine=engine, **kwargs)
    if primary.success:
        return primary
    enabled = _env_bool("XY_SLIDER_DRISSION_FALLBACK", True) if fallback_enabled is None else bool(fallback_enabled)
    if not enabled:
        return primary
    fallback = _run_drissionpage_fallback(
        url,
        user_id=user_id,
        existing_cookies_str=str(getattr(slider, "initial_cookies", "") or ""),
        headless=bool(getattr(slider, "headless", True)) if fallback_headless is None else bool(fallback_headless),
        max_retries=fallback_max_retries,
        handler_factory=handler_factory,
    )
    return fallback if fallback.success else primary


async def run_slider_async_strict(
    slider: Any, url: str, *, engine: Optional[str] = DEFAULT_SLIDER_ENGINE, **kwargs: Any
):
    success, cookies = await _invoke_async(slider, url, **kwargs)
    return validate_slider_result(success, cookies, engine=engine)


async def run_slider_async_with_fallback(
    slider: Any,
    url: str,
    *,
    engine: Optional[str] = DEFAULT_SLIDER_ENGINE,
    fallback_enabled: Optional[bool] = None,
    remote_enabled: Optional[bool] = None,
    remote_config: Optional[Tuple[str, str]] = None,
    remote_timeout: int = 60,
    fallback_headless: Optional[bool] = None,
    fallback_max_retries: int = 3,
    handler_factory: Optional[Callable[..., Any]] = None,
    **kwargs: Any,
):
    user_id = str(getattr(slider, "user_id", None) or getattr(slider, "pure_user_id", None) or "unknown")
    use_remote = _env_bool("XY_SLIDER_REMOTE_ENABLED", False) if remote_enabled is None else bool(remote_enabled)
    remote_url, remote_secret = remote_config or _remote_config_from_env()
    if use_remote and remote_url and remote_secret:
        remote_result = await asyncio.to_thread(
            _call_remote_solve,
            url,
            user_id=user_id,
            remote_url=remote_url,
            remote_secret=remote_secret,
            timeout=remote_timeout,
        )
        if remote_result.success:
            return remote_result

    primary = await run_slider_async_strict(slider, url, engine=engine, **kwargs)
    if primary.success:
        return primary
    enabled = _env_bool("XY_SLIDER_DRISSION_FALLBACK", True) if fallback_enabled is None else bool(fallback_enabled)
    if not enabled:
        return primary
    fallback = await asyncio.to_thread(
        _run_drissionpage_fallback,
        url,
        user_id=user_id,
        existing_cookies_str=str(getattr(slider, "initial_cookies", "") or ""),
        headless=bool(getattr(slider, "headless", True)) if fallback_headless is None else bool(fallback_headless),
        max_retries=fallback_max_retries,
        handler_factory=handler_factory,
    )
    return fallback if fallback.success else primary


__all__ = [
    "SliderVerificationResult",
    "extract_x5_cookies",
    "has_x5_cookie",
    "parse_cookie_string",
    "run_slider_async_strict",
    "run_slider_async_with_fallback",
    "run_slider_strict",
    "run_slider_with_fallback",
    "validate_slider_result",
]
