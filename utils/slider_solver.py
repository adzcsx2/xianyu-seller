"""Async Playwright slider solver adapted from ``xianyu-auto-bot``.

It deliberately returns the browser Cookie snapshot without declaring strict
success itself.  ``slider_orchestrator`` then requires an x5/x5sec ticket,
which keeps visual-only passes from being written back as valid sessions.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import psutil
from loguru import logger
from playwright.async_api import async_playwright

from utils.slider_image_match import SliderImageMatcher
from utils.slider_stealth_patch import STEALTH_INIT_SCRIPT, STEALTH_LAUNCH_ARGS
from utils.slider_trajectory import generate_trajectory
from utils.slider_trajectory_pool import safe_storage_key, trajectory_pool


def _kill_chromium(pid: int) -> None:
    try:
        process = psutil.Process(pid)
        name = (process.name() or "").lower()
        if "chrome" not in name and "chromium" not in name:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return


class SliderSolver:
    SLIDER_BTN = "#nc_1_n1z"
    SLIDER_TRACK = "#nc_1_n1t"
    MAX_RETRIES = 3

    def __init__(
        self,
        cookie_id: str = "default",
        cookies_str: str = "",
        headless: bool = True,
        proxy: Optional[Dict[str, Any]] = None,
        trajectory_mode: str = "auto",
        max_retries: int = 3,
        user_id: Optional[str] = None,
        initial_cookies: Optional[str] = None,
        config: Any = None,
        **_: Any,
    ):
        self.cookie_id = str(user_id or cookie_id)
        self.user_id = self.cookie_id
        self.pure_user_id = self.cookie_id.split("_", 1)[0]
        self.cookies_str = str(initial_cookies if initial_cookies is not None else cookies_str or "").strip()
        self.initial_cookies = self.cookies_str
        self.headless = bool(headless)
        self.proxy = dict(proxy or {})
        self.trajectory_mode = trajectory_mode
        self.max_retries = max(1, int(max_retries or self.MAX_RETRIES))
        self.config = config
        self.last_fallback_used: Optional[str] = None
        self._playwright = None
        self.context = None
        self.page = None
        self._cdp = None
        self._result_event = asyncio.Event()
        self._slide_code: Optional[int] = None
        self._current_trajectory = None
        self._chromium_pid: Optional[int] = None
        self.profile_dir = Path(__file__).resolve().parent.parent / "browser_data" / f"slider_{safe_storage_key(self.pure_user_id)}"
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    async def solve(self, verify_url: str):
        self.last_fallback_used = None
        started = time.monotonic()
        logger.info("[{}] slider solve started mode={}", self.pure_user_id, self.trajectory_mode)
        try:
            await self._init_browser()
            await self._load_page(verify_url)
            if not await self._wait_slider():
                return await self._fallback_or_fail(verify_url, "slider_not_found")
            distance = await self._calc_distance_multi_source()
            if not distance or distance <= 0:
                return await self._fallback_or_fail(verify_url, "distance_not_found")

            if self.trajectory_mode in ("auto", "recorded"):
                recorded = trajectory_pool.load_best_trajectory(self.pure_user_id, distance)
                if recorded:
                    for attempt in range(1, self.max_retries + 1):
                        await self._do_slide(distance, attempt, recorded.get("points"))
                        code = await self._wait_result()
                        logger.info("[{}] recorded attempt={} code={}", self.pure_user_id, attempt, code)
                        if code in (0, 1000):
                            cookies = await self._get_cookies()
                            logger.success("[{}] slider visual pass via recorded trajectory", self.pure_user_id)
                            return True, cookies
                        if attempt < self.max_retries:
                            await self._retry_slider()
                            distance = await self._calc_distance_multi_source() or distance
                    if self.trajectory_mode == "recorded":
                        return await self._fallback_or_fail(verify_url, "recorded_retries_exhausted")

            for attempt in range(1, self.max_retries + 1):
                trajectory = generate_trajectory(distance, attempt)
                self._current_trajectory = trajectory
                await self._do_slide(distance, attempt, trajectory)
                code = await self._wait_result()
                logger.info("[{}] generated attempt={} code={}", self.pure_user_id, attempt, code)
                if code in (0, 1000):
                    cookies = await self._get_cookies()
                    trajectory_pool.save_trajectory(
                        trajectory,
                        self.pure_user_id,
                        distance,
                        True,
                        verify_url,
                        (time.monotonic() - started) * 1000,
                    )
                    logger.success("[{}] slider visual pass via generated trajectory", self.pure_user_id)
                    return True, cookies
                if attempt < self.max_retries:
                    await self._retry_slider()
                    distance = await self._calc_distance_multi_source() or distance
            return await self._fallback_or_fail(verify_url, "auto_retries_exhausted")
        except Exception as exc:
            logger.exception("[{}] slider solver error: {}", self.pure_user_id, exc)
            return await self._fallback_or_fail(verify_url, f"solver_exception={type(exc).__name__}")
        finally:
            await self._close()

    async def _retry_slider(self) -> None:
        await asyncio.sleep(1.0 + random.random())
        self._result_event.clear()
        self._slide_code = None

    async def _fallback_or_fail(self, verify_url: str, reason: str):
        logger.warning("[{}] automatic slider failed: {}", self.pure_user_id, reason)
        if self.trajectory_mode in ("auto", "recorded") and os.getenv("XY_SLIDER_REMOTE_FALLBACK", "1").lower() not in {"0", "false", "no"}:
            try:
                result = await self._fallback_to_remote(verify_url)
                if result[0]:
                    return result
            except Exception as exc:
                logger.warning("[{}] remote fallback failed: {}", self.pure_user_id, exc)
        return False, None

    async def _fallback_to_remote(self, verify_url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        try:
            from utils.captcha_remote_control import captcha_controller
        except ImportError:
            return False, None
        if not self.page:
            await self._init_browser()
            await self._load_page(verify_url)
            await self._wait_slider()
        session_id = f"slider_fallback_{self.pure_user_id}_{int(time.time())}"
        try:
            await captcha_controller.create_session(session_id, self.page)
        except TypeError:
            await captcha_controller.create_session(session_id, self.page, owner_user_id=None)
        self.last_fallback_used = "remote"
        logger.warning("[{}] remote slider session opened: {}", self.pure_user_id, session_id)
        deadline = time.time() + max(30, int(os.getenv("XY_SLIDER_REMOTE_TIMEOUT", "180")))
        try:
            while time.time() < deadline:
                if await captcha_controller.check_completion(session_id):
                    cookies = await self._get_cookies()
                    logger.success("[{}] remote slider completed", self.pure_user_id)
                    try:
                        recording = captcha_controller.finish_recording(session_id)
                        if recording and recording.get("points"):
                            trajectory_pool.save_trajectory(
                                recording["points"], self.pure_user_id,
                                recording.get("distance", 0), True, verify_url,
                                recording.get("duration_ms", 0),
                            )
                    except Exception as exc:
                        logger.warning("[{}] remote trajectory save failed: {}", self.pure_user_id, exc)
                    return True, cookies
                await asyncio.sleep(2)
        finally:
            try:
                await captcha_controller.close_session(session_id)
            except Exception:
                pass
        logger.warning("[{}] remote slider timed out", self.pure_user_id)
        return False, None

    async def _init_browser(self) -> None:
        self._playwright = await async_playwright().start()
        launch_kwargs: Dict[str, Any] = {
            "headless": self.headless,
            "args": STEALTH_LAUNCH_ARGS,
            "viewport": {"width": 1920, "height": 1080},
        }
        host = self.proxy.get("proxy_host") or self.proxy.get("host")
        port = self.proxy.get("proxy_port") or self.proxy.get("port")
        if host and port:
            scheme = str(self.proxy.get("proxy_type") or self.proxy.get("type") or "http").lower()
            launch_kwargs["proxy"] = {
                "server": f"{scheme}://{host}:{port}",
                **({"username": str(self.proxy["proxy_user"])} if self.proxy.get("proxy_user") else {}),
                **({"password": str(self.proxy["proxy_pass"])} if self.proxy.get("proxy_pass") else {}),
            }
        self.context = await self._playwright.chromium.launch_persistent_context(str(self.profile_dir), **launch_kwargs)
        self.page = await self.context.new_page()
        await self.page.add_init_script(STEALTH_INIT_SCRIPT)
        await self._inject_cookies()
        self.page.on("response", self._on_response)
        try:
            self._cdp = await self.context.new_cdp_session(self.page)
        except Exception:
            self._cdp = None
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                if "chrome" not in name and "chromium" not in name:
                    continue
                if any(str(self.profile_dir) in str(arg) for arg in (process.info.get("cmdline") or [])):
                    self._chromium_pid = process.info["pid"]
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    async def _inject_cookies(self) -> None:
        if not self.cookies_str:
            return
        hostname = urlparse("https://www.goofish.com").hostname or "www.goofish.com"
        cookies = []
        for part in self.cookies_str.split(";"):
            if "=" not in part:
                continue
            name, value = part.strip().split("=", 1)
            if name.strip():
                cookies.append({"name": name.strip(), "value": value.strip(), "domain": f".{hostname.split('.', 1)[-1]}", "path": "/"})
        if cookies:
            await self.context.add_cookies(cookies)

    async def _load_page(self, url: str) -> None:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

    async def _wait_slider(self, timeout: float = 15) -> bool:
        for selector in (self.SLIDER_BTN, ".nc_iconfont", ".btn_slide", ".sm-btn"):
            try:
                await self.page.wait_for_selector(selector, state="visible", timeout=int(timeout * 1000))
                logger.info("[{}] slider found via {}", self.pure_user_id, selector)
                return True
            except Exception:
                continue
        return False

    async def _calc_distance_multi_source(self) -> Optional[float]:
        dom_distance = await self._calc_distance_dom()
        image_distance = await self._calc_distance_image()
        if image_distance and dom_distance and 0.7 <= image_distance / dom_distance <= 1.3:
            return image_distance
        if dom_distance and dom_distance > 0:
            return dom_distance
        try:
            track_width = await self.page.eval_on_selector(
                ".nc_scale, [class*=track]", "element => element.offsetWidth"
            )
            return float(track_width) * 0.85 if track_width else None
        except Exception:
            return None

    async def _calc_distance_dom(self) -> Optional[float]:
        try:
            result = await self.page.evaluate("""() => {
                const button = document.querySelector('#nc_1_n1z');
                const track = document.querySelector('#nc_1_n1t');
                if (!button || !track) return 0;
                return track.getBoundingClientRect().width - button.getBoundingClientRect().width;
            }""")
            return float(result) if result and float(result) > 0 else None
        except Exception:
            return None

    async def _calc_distance_image(self) -> Optional[float]:
        try:
            background = await self.page.query_selector("#nc_1_n1t img, .nc_scale img, img[id*=bg]")
            piece = await self.page.query_selector("#nc_1_n1z img, img[id*=slide]")
            if not background or not piece:
                return None
            result = SliderImageMatcher.find_gap_from_bytes(
                await background.screenshot(type="png"), await piece.screenshot(type="png")
            )
            return float(result) if result else None
        except Exception:
            return None

    async def _do_slide(self, distance: float, attempt: int, trajectory) -> None:
        button = await self.page.query_selector(self.SLIDER_BTN)
        if not button:
            return
        box = await button.bounding_box()
        if not box:
            return
        start_x = box["x"] + box["width"] / 2 + random.uniform(-2.5, 2.5)
        start_y = box["y"] + box["height"] / 2 + random.uniform(-2.5, 2.5)
        self._result_event.clear()
        self._slide_code = None
        cdp = self._cdp
        try:
            if cdp:
                await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": start_x, "y": start_y, "button": "none", "pointerType": "mouse"})
                await asyncio.sleep(trajectory[0][2] / 1000)
                await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": start_x, "y": start_y, "button": "left", "clickCount": 1, "pointerType": "mouse"})
                previous_x, previous_y = start_x, start_y
                for dx, dy, delay in trajectory[1:]:
                    x, y = start_x + dx, start_y + dy
                    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "left", "pointerType": "mouse", "movementX": x - previous_x, "movementY": y - previous_y})
                    previous_x, previous_y = x, y
                    await asyncio.sleep(delay / 1000)
                await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": previous_x, "y": previous_y, "button": "left", "clickCount": 1, "pointerType": "mouse"})
                return
        except Exception as exc:
            logger.warning("[{}] CDP drag failed, using Playwright: {}", self.pure_user_id, exc)
            self._cdp = None
        await self.page.mouse.move(start_x - random.uniform(3, 8), start_y + random.uniform(1, 4))
        await self.page.mouse.move(start_x, start_y)
        await asyncio.sleep(0.05)
        await self.page.mouse.down()
        for dx, dy, delay in trajectory:
            await self.page.mouse.move(start_x + dx, start_y + dy)
            await asyncio.sleep(delay / 1000)
        await self.page.mouse.up()

    async def _on_response(self, response) -> None:
        if "/slide?" not in response.url and "/_____tmd_____/slide" not in response.url:
            return
        try:
            payload = json.loads((await response.body()).decode("utf-8", errors="ignore"))
            self._slide_code = int(payload.get("code", -1))
            logger.info("[{}] SLIDER_RESULT code={}", self.pure_user_id, self._slide_code)
            self._result_event.set()
        except Exception:
            return

    async def _wait_result(self, timeout: float = 6) -> int:
        try:
            await asyncio.wait_for(self._result_event.wait(), timeout)
        except asyncio.TimeoutError:
            return -1
        return self._slide_code if self._slide_code is not None else -1

    async def _get_cookies(self) -> Dict[str, str]:
        try:
            return {item["name"]: item["value"] for item in await self.context.cookies()}
        except Exception:
            return {}

    async def _close(self) -> None:
        for resource in (self.context, self._playwright):
            if resource is not None:
                try:
                    await resource.close() if resource is self.context else await resource.stop()
                except Exception:
                    pass
        if self._chromium_pid:
            await asyncio.to_thread(_kill_chromium, self._chromium_pid)
            self._chromium_pid = None


__all__ = ["SliderSolver"]
