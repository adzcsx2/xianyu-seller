"""密码登录不能阻塞 API，也不能占住槽位导致下一次登录永远排队。"""

import asyncio
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app import reply_server
from utils import xianyu_slider_stealth as slider_module
from XianyuAutoAsync import XianyuLive


class PasswordLoginLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = {'user_id': 7, 'username': 'seller'}
        self.session = {'status': 'processing', 'user_id': 7,
                        'account_id': 'test-login', 'timestamp': time.time()}
        reply_server.password_login_sessions['test-session'] = self.session
        self.instances = []
        self.thread_ids = []
        self.manager = slider_module.concurrency_manager
        self.active_patch = patch.object(self.manager, 'active_instances', {})
        self.active_patch.start()

    def tearDown(self):
        for instance in self.instances:
            instance.close_browser()
        self.active_patch.stop()
        reply_server.password_login_sessions.clear()
        XianyuLive._last_password_login_time.pop('test-login', None)

    async def run_manual(self):
        await reply_server._execute_password_login(
            'test-session', 'test-login', 'test-user', 'test-password', False, 7, self.user,
        )
        # 兼容旧实现里的 daemon 线程，保证失败断言前线程已经完成。
        for _ in range(100):
            if self.session['status'] != 'processing':
                break
            await asyncio.sleep(0.01)

    def make_live(self):
        live = XianyuLive.__new__(XianyuLive)
        live.cookie_id = 'test-login'
        live.cookies_str = 'old-cookie'
        live.send_token_refresh_notification = AsyncMock()
        live._update_cookies_and_restart = AsyncMock(return_value=True)
        return live

    def test_password_verification_state_preserves_sms_instruction(self):
        session = {'status': 'processing'}

        reply_server.set_password_login_verification_state(
            session,
            '账号密码登录需要短信验证，请按验证页面提示主动发送短信',
        )

        self.assertEqual(session['status'], 'verification_required')
        self.assertEqual(session['verification_type'], 'sms')
        self.assertEqual(
            session['verification_message'],
            '账号密码登录需要短信验证，请按验证页面提示主动发送短信',
        )

    async def test_password_status_returns_sms_metadata_to_frontend(self):
        self.session.update(
            status='verification_required',
            verification_type='sms',
            verification_message='请按验证页面提示主动发送短信，完成后会自动继续登录',
        )

        result = await reply_server.check_password_login_status(
            'test-session', current_user=self.user,
        )

        self.assertEqual(result['status'], 'verification_required')
        self.assertEqual(result['verification_type'], 'sms')
        self.assertIn('主动发送短信', result['message'])

    async def test_manual_constructor_runs_off_event_loop_and_cleans_instance(self):
        loop_thread = threading.get_ident()
        real_class = slider_module.XianyuSliderStealth

        def create(**kwargs):
            self.thread_ids.append(threading.get_ident())
            instance = real_class(**kwargs)
            self.instances.append(instance)
            instance.login_with_password_playwright = Mock(return_value=None)
            return instance

        with patch.object(slider_module, 'XianyuSliderStealth', side_effect=create):
            await self.run_manual()
        self.assertNotEqual(self.thread_ids[0], loop_thread)
        self.assertEqual(self.session['status'], 'failed')
        self.assertIsNone(self.session.get('slider_instance'))
        self.assertIsNone(self.instances[0].temp_dir)
        self.assertEqual(self.manager.active_instances, {})

    async def test_constructor_wait_does_not_block_other_requests(self):
        ticks = []

        async def probe():
            await asyncio.sleep(0.02)
            ticks.append(time.monotonic())

        def fail_after_wait(**_kwargs):
            time.sleep(0.2)
            raise RuntimeError('等待槽位超时')

        with patch.object(slider_module, 'XianyuSliderStealth', side_effect=fail_after_wait):
            start = time.monotonic()
            await asyncio.gather(self.run_manual(), probe())
        self.assertLess(ticks[0] - start, 0.15)
        self.assertEqual(self.session['status'], 'failed')
        self.assertIn('等待槽位超时', self.session['error'])

    async def test_auto_refresh_releases_slot_on_success_failure_and_exception(self):
        real_class = slider_module.XianyuSliderStealth
        loop_thread = threading.get_ident()
        for outcome in (None, RuntimeError('browser failed'), {'unb': 'test-login'}):
            with self.subTest(outcome=type(outcome).__name__):
                XianyuLive._last_password_login_time.pop('test-login', None)

                def create(**kwargs):
                    self.thread_ids.append(threading.get_ident())
                    instance = real_class(**kwargs)
                    self.instances.append(instance)
                    instance.login_with_password_playwright = Mock(
                        side_effect=outcome if isinstance(outcome, Exception) else None,
                        return_value=outcome,
                    )
                    return instance

                live = self.make_live()
                with (
                    patch.object(slider_module, 'XianyuSliderStealth', side_effect=create),
                    patch.object(reply_server.db_manager, 'get_cookie_details', return_value={
                        'username': 'test-user', 'password': 'test-password',
                    }),
                    patch('XianyuAutoAsync.log_captcha_event'),
                ):
                    result = await live._try_password_login_refresh()
                try:
                    self.assertEqual(result, isinstance(outcome, dict))
                    self.assertEqual(self.manager.active_instances, {})
                    self.assertIsNone(self.instances[-1].temp_dir)
                    self.assertNotEqual(self.thread_ids[-1], loop_thread)
                finally:
                    self.instances[-1].close_browser()

    async def test_auto_refresh_failure_starts_cooldown_before_next_reconnect(self):
        created_instances = []

        class FailedSlider:
            def __init__(self, **_kwargs):
                created_instances.append(self)

            def login_with_password_playwright(self, **_kwargs):
                return None

            def close_browser(self):
                return None

        live = self.make_live()
        with (
            patch(
                'utils.slider_runtime.load_slider_class',
                return_value=(FailedSlider, 'slidex-test'),
            ),
            patch.object(reply_server.db_manager, 'get_cookie_details', return_value={
                'username': 'test-user', 'password': 'test-password',
            }),
            patch('XianyuAutoAsync.log_captcha_event'),
        ):
            first_result = await live._try_password_login_refresh()
            second_result = await live._try_password_login_refresh()

        self.assertFalse(first_result)
        self.assertFalse(second_result)
        self.assertEqual(
            len(created_instances),
            1,
            '失败的密码登录没有进入冷却，重连循环会持续触发浏览器风控',
        )


if __name__ == '__main__':
    unittest.main()
