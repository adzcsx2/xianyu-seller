import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import reply_server
from app.db_manager import DBManager


class AdminAutoLoginTests(unittest.TestCase):
    def setUp(self):
        reply_server.SESSION_TOKENS.clear()

    def tearDown(self):
        reply_server.SESSION_TOKENS.clear()

    def test_empty_login_creates_admin_session_when_admin_login_is_disabled(self):
        admin = {
            "id": 17,
            "username": "env-admin",
            "is_active": True,
        }

        with (
            patch.object(reply_server, "ADMIN_USERNAME", "env-admin"),
            patch.object(reply_server, "ADMIN_LOGIN_ENABLED", False, create=True),
            patch.object(
                reply_server.db_manager,
                "verify_user_password",
                return_value=False,
            ) as verify_password,
            patch.object(
                reply_server.db_manager,
                "get_user_by_username",
                return_value=admin,
            ),
        ):
            response = asyncio.run(reply_server.login(reply_server.LoginRequest()))

        self.assertTrue(response.success)
        self.assertTrue(response.is_admin)
        self.assertEqual(response.username, "env-admin")
        self.assertIn(response.token, reply_server.SESSION_TOKENS)
        verify_password.assert_not_called()

    def test_empty_login_requires_credentials_when_admin_login_is_enabled(self):
        with (
            patch.object(reply_server, "ADMIN_USERNAME", "env-admin"),
            patch.object(reply_server, "ADMIN_LOGIN_ENABLED", True, create=True),
            patch.object(
                reply_server.db_manager,
                "verify_user_password",
                return_value=True,
            ) as verify_password,
        ):
            response = asyncio.run(reply_server.login(reply_server.LoginRequest()))

        self.assertFalse(response.success)
        self.assertIsNone(response.token)
        self.assertEqual(reply_server.SESSION_TOKENS, {})
        self.assertEqual(response.message, "请提供有效的登录信息")
        verify_password.assert_not_called()

    def test_admin_login_enabled_accepts_explicit_credentials(self):
        admin = {
            "id": 17,
            "username": "env-admin",
            "is_active": True,
        }

        with (
            patch.object(reply_server, "ADMIN_USERNAME", "env-admin"),
            patch.object(reply_server, "ADMIN_LOGIN_ENABLED", True),
            patch.object(
                reply_server.db_manager,
                "verify_user_password",
                return_value=True,
            ) as verify_password,
            patch.object(
                reply_server.db_manager,
                "get_user_by_username",
                return_value=admin,
            ),
        ):
            response = asyncio.run(
                reply_server.login(
                    reply_server.LoginRequest(
                        username="env-admin",
                        password="env-password",
                    )
                )
            )

        self.assertTrue(response.success)
        self.assertTrue(response.is_admin)
        verify_password.assert_called_once_with("env-admin", "env-password")

    def test_default_password_warning_still_checks_builtin_default(self):
        with (
            patch.object(reply_server, "ADMIN_USERNAME", "env-admin"),
            patch.object(
                reply_server.db_manager,
                "verify_user_password",
                return_value=False,
            ) as verify_password,
        ):
            response = asyncio.run(
                reply_server.check_default_password(
                    {"username": "env-admin", "is_admin": True}
                )
            )

        self.assertFalse(response["using_default"])
        verify_password.assert_called_once_with("env-admin", "admin123")


class AdminEnvironmentBootstrapTests(unittest.TestCase):
    def test_new_database_bootstraps_configured_admin_username_and_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "admin-env.db")
            with patch.dict(
                os.environ,
                {
                    "ADMIN_USERNAME": "env-admin",
                    "ADMIN_PASSWORD": "env-password",
                },
            ):
                database = DBManager(db_path)

            try:
                self.assertIsNotNone(database.get_user_by_username("env-admin"))
                self.assertTrue(
                    database.verify_user_password("env-admin", "env-password")
                )
                self.assertIsNone(database.get_user_by_username("admin"))
            finally:
                database.conn.close()

    def test_reopened_database_syncs_admin_to_environment_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "admin-redeploy.db")
            with patch.dict(
                os.environ,
                {
                    "ADMIN_USERNAME": "admin",
                    "ADMIN_PASSWORD": "old-password",
                },
            ):
                database = DBManager(db_path)
                database.conn.close()

            with patch.dict(
                os.environ,
                {
                    "ADMIN_USERNAME": "env-admin",
                    "ADMIN_PASSWORD": "new-password",
                },
            ):
                database = DBManager(db_path)

            try:
                self.assertIsNotNone(database.get_user_by_username("env-admin"))
                self.assertTrue(
                    database.verify_user_password("env-admin", "new-password")
                )
                self.assertIsNone(database.get_user_by_username("admin"))
            finally:
                database.conn.close()

    def test_reopened_database_without_admin_environment_keeps_existing_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "admin-no-env.db")
            with patch.dict(
                os.environ,
                {
                    "ADMIN_USERNAME": "admin",
                    "ADMIN_PASSWORD": "existing-password",
                },
            ):
                database = DBManager(db_path)
                database.conn.close()

            with patch.dict(os.environ, {}, clear=True):
                database = DBManager(db_path)

            try:
                self.assertTrue(
                    database.verify_user_password("admin", "existing-password")
                )
                self.assertFalse(database.verify_user_password("admin", "admin123"))
            finally:
                database.conn.close()


if __name__ == "__main__":
    unittest.main()
