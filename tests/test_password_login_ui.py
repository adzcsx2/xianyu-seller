"""真实页面 → HTTP 接口 → 工作线程；仅替换闲鱼浏览器和账号数据。"""

import json
import socket
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import uvicorn
from playwright.sync_api import sync_playwright, expect

from app import reply_server
from utils import xianyu_slider_stealth as slider_module


class PasswordLoginUiTests(unittest.TestCase):
    def test_click_retry_and_success_keep_api_responsive(self):
        account = {
            'id': 'ui-login-test', 'user_id': 7, 'enabled': False,
            'username': 'test-user', 'login_password': 'test-password',
            'nickname': '密码登录测试账号', 'value': '',
        }
        token = 'password-login-ui-test-token'
        user = {'user_id': 7, 'username': 'test-seller', 'timestamp': time.time()}
        reply_server.SESSION_TOKENS[token] = user
        instances = []
        outcomes = iter([None, RuntimeError('测试浏览器启动失败'), {'unb': account['id']}])
        real_class = slider_module.XianyuSliderStealth
        temp_live = Mock()
        temp_live._refresh_cookies_via_browser = AsyncMock(return_value=False)
        constructor_entered = threading.Event()
        release_constructor = threading.Event()

        def create(**kwargs):
            constructor_entered.set()
            if not release_constructor.wait(5):
                raise RuntimeError('测试发现接口被构造器阻塞')
            instance = real_class(**kwargs)
            instances.append(instance)
            outcome = next(outcomes)
            instance.login_with_password_playwright = Mock(
                side_effect=outcome if isinstance(outcome, Exception) else None,
                return_value=outcome,
            )
            return instance

        # 绑定随机端口，避免触碰正在运行的 8080 服务。
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = uvicorn.Server(uvicorn.Config(reply_server.app, lifespan='off', log_level='error'))
        server_thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        try:
            with (
                patch.object(slider_module.concurrency_manager, 'active_instances', {}),
                patch.object(slider_module, 'XianyuSliderStealth', side_effect=create),
                patch.object(reply_server.db_manager, 'get_cookie_details', return_value=account),
                patch.object(reply_server.db_manager, 'get_all_cookies', return_value={account['id']: ''}),
                patch.object(reply_server.db_manager, 'update_cookie_account_info', return_value=True) as save,
                patch.object(reply_server.cookie_manager, 'manager', None),
                patch('XianyuAutoAsync.XianyuLive', return_value=temp_live),
                sync_playwright() as playwright,
            ):
                server_thread.start()
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(0.02)
                self.assertTrue(server.started)
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.add_init_script(f"localStorage.setItem('auth_token', '{token}')")
                    page.route('**/cookies/details', lambda route: route.fulfill(
                        content_type='application/json', body=json.dumps([account]),
                    ))
                    page.goto(origin)
                    page.get_by_role('button', name='账号管理', exact=True).click()
                    for expected in ('登录失败，请检查账号密码是否正确', '测试浏览器启动失败',
                                     f"账号 {account['id']} 登录成功"):
                        constructor_entered.clear()
                        release_constructor.clear()
                        with page.expect_response(lambda response: response.url == origin + '/password-login') as pending:
                            page.get_by_role('button', name='账号密码登录', exact=True).click()
                        response = pending.value
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.json()['success'])
                        self.assertTrue(constructor_entered.wait(1))
                        # 在构造器尚未完成时，轮询和 health 必须已经可用。
                        session_id = response.json()['session_id']
                        status = page.request.get(origin + '/password-login/check/' + session_id,
                                                  headers={'Authorization': f'Bearer {token}'}, timeout=1000)
                        self.assertEqual(status.json()['status'], 'processing')
                        # 隔离环境未启动监听管理器，health 应及时返回明确的 503。
                        health = page.request.get(origin + '/health', timeout=1000)
                        self.assertEqual(health.status, 503)
                        self.assertEqual(health.json()['services']['database'], 'ok')
                        release_constructor.set()
                        expect(page.get_by_text(expected, exact=True)).to_be_visible(timeout=10000)
                        page.get_by_role('button', name='关闭账号密码登录', exact=True).click()
                        self.assertEqual(slider_module.concurrency_manager.active_instances, {})
                    save.assert_called_once()
                    self.assertTrue(all(instance.temp_dir is None for instance in instances))
                finally:
                    browser.close()
        finally:
            release_constructor.set()
            server.should_exit = True
            if server_thread.ident:
                server_thread.join(10)
            listener.close()
            reply_server.SESSION_TOKENS.pop(token, None)
            reply_server.password_login_sessions.clear()


if __name__ == '__main__':
    unittest.main()
