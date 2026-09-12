"""Select the reference slidex runtime with a local compatibility fallback."""
from __future__ import annotations


class LegacySlidexConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def load_slider_class():
    try:
        from slidex.stealth import XianyuSliderStealth
        return XianyuSliderStealth, "slidex"
    except ModuleNotFoundError as exc:
        if exc.name != "slidex":
            raise
        from utils.xianyu_slider_stealth import XianyuSliderStealth
        return XianyuSliderStealth, "legacy"


def load_slider_runtime():
    try:
        from slidex.stealth import XianyuSliderStealth, probe_cookie_verification_from_cookie
        from slidex import SlidexConfig
        from slidex._concurrency import concurrency_manager
        return XianyuSliderStealth, probe_cookie_verification_from_cookie, SlidexConfig, concurrency_manager, "slidex"
    except ModuleNotFoundError as exc:
        if exc.name != "slidex":
            raise
        from utils.xianyu_slider_stealth import XianyuSliderStealth, concurrency_manager

        def probe_cookie_verification_from_cookie(*_args, **_kwargs):
            return None

        return XianyuSliderStealth, probe_cookie_verification_from_cookie, LegacySlidexConfig, concurrency_manager, "legacy"


def create_slider_instance(slider_cls, **kwargs):
    try:
        return slider_cls(**kwargs)
    except TypeError:
        kwargs.pop("slidex_config", None)
        kwargs.pop("config", None)
        return slider_cls(**kwargs)


__all__ = ["LegacySlidexConfig", "create_slider_instance", "load_slider_class", "load_slider_runtime"]
