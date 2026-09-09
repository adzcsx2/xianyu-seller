import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import reply_server


class PasswordLoginScopeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reply_server.password_login_sessions.clear()

    def tearDown(self):
        reply_server.password_login_sessions.clear()

    async def test_password_login_rejects_account_not_owned_by_current_user(self):
        current_user = {'user_id': 7, 'username': 'seller'}

        with patch.object(
            reply_server.db_manager,
            'get_cookie_details',
            return_value={'id': 'other-account', 'user_id': 99},
        ), patch.object(reply_server.asyncio, 'create_task') as create_task:
            with self.assertRaises(HTTPException) as context:
                await reply_server.password_login(
                    {
                        'account_id': 'other-account',
                        'account': 'seller@example.com',
                        'password': 'password',
                    },
                    current_user,
                )

        self.assertEqual(context.exception.status_code, 403)
        create_task.assert_not_called()


if __name__ == '__main__':
    unittest.main()
