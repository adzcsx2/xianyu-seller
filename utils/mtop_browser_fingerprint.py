"""为 MTOP 请求与人工验证浏览器提供同一套浏览器指纹。"""

from typing import Dict

from app.config import DEFAULT_HEADERS


_FALLBACK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
)
_FALLBACK_SEC_CH_UA = (
    '"Not=A?Brand";v="99", "Microsoft Edge";v="151", '
    '"Chromium";v="151"'
)


def _configured(name: str, fallback: str) -> str:
    """读取非空字符串配置，防止空值把关键指纹头抹掉。"""
    value = DEFAULT_HEADERS.get(name, fallback)
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def get_browser_fingerprint_headers() -> Dict[str, str]:
    """返回 MTOP 与滑块浏览器共用的 UA / Client Hints。"""
    return {
        "user-agent": _configured("user-agent", _FALLBACK_USER_AGENT),
        "sec-ch-ua": _configured("sec-ch-ua", _FALLBACK_SEC_CH_UA),
        "sec-ch-ua-mobile": _configured("sec-ch-ua-mobile", "?0"),
        "sec-ch-ua-platform": _configured("sec-ch-ua-platform", '"Windows"'),
    }


def build_mtop_request_headers(cookies_str: str) -> Dict[str, str]:
    """构造 Token/惩罚 URL 请求头，确保 x5sec 使用相同指纹。"""
    fingerprint = get_browser_fingerprint_headers()
    return {
        "accept": "application/json",
        "accept-language": _configured(
            "accept-language", "zh-CN,zh;q=0.9,en;q=0.8"
        ),
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "pragma": "no-cache",
        "priority": "u=1, i",
        **fingerprint,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "referer": "https://www.goofish.com/",
        "origin": "https://www.goofish.com",
        "cookie": (cookies_str or "").replace("\n", "").replace("\r", ""),
    }


def get_playwright_context_options() -> Dict[str, object]:
    """把同一套 UA / Client Hints 转成 Playwright context 参数。"""
    fingerprint = get_browser_fingerprint_headers()
    return {
        "user_agent": fingerprint.pop("user-agent"),
        "extra_http_headers": fingerprint,
    }
