import asyncio
import base64
import json
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app import reply_server
from XianyuAutoAsync import XianyuLive


class FeatureRuntimeGateTests(unittest.IsolatedAsyncioTestCase):
    def _live(self):
        live = object.__new__(XianyuLive)
        live.cookie_id = "runtime-gate-test"
        live.myid = "seller-id"
        live.cookies_str = "cookie=redacted"
        live._thanked_receipts = set()
        live._buyer_interaction_triggering = False
        live.order_status_handler = None
        live.last_message_received_time = 0
        return live

    async def test_auto_delivery_gate_blocks_normal_and_bargain_paths_before_db(self):
        live = self._live()
        live.is_feature_enabled = Mock(return_value=False)
        with patch("app.db_manager.db_manager.get_item_info") as get_item:
            result = await live._handle_auto_delivery(
                None, {}, "buyer", "buyer-id", "item-id", "chat-id", "now"
            )
        self.assertEqual(result["code"], "feature_disabled")
        get_item.assert_not_called()

        with patch("app.secure_freeshipping.SecureFreeshipping") as secure:
            result = await live.auto_freeshipping("order", "item", "buyer")
        self.assertEqual(result["code"], "feature_disabled")
        secure.assert_not_called()

    async def test_buyer_interaction_and_auto_reply_gates_block_side_effects(self):
        live = self._live()
        live.is_feature_enabled = Mock(return_value=False)
        live._extract_message_id = Mock(return_value="message-id")
        live._run_buyer_interactions = AsyncMock()

        with patch("app.db_manager.db_manager.get_buyer_interaction_settings") as get_settings:
            self.assertFalse(await live.send_post_receipt_thanks(None, "chat", "buyer"))
            self.assertFalse(await live.trigger_buyer_interactions_now("收货"))
        get_settings.assert_not_called()
        live._schedule_debounced_reply = XianyuLive._schedule_debounced_reply.__get__(live)
        self.assertFalse(
            await live._schedule_debounced_reply(
                "chat", {}, None, "buyer", "buyer-id", "你好", "item", "now"
            )
        )
        live._extract_message_id.assert_not_called()

    async def test_order_event_prefetch_is_skipped_but_chat_reply_stays_available(self):
        live = self._live()
        live.is_feature_enabled = Mock(
            side_effect=lambda key: key != "feature_orders_enabled"
        )
        live.send_notification = AsyncMock()
        live._schedule_debounced_reply = AsyncMock()
        live.extract_item_id_from_message = Mock(return_value=None)
        live._extract_order_id = Mock(return_value="order-id")
        live.fetch_order_real_values = AsyncMock()
        live.fetch_order_detail_info = AsyncMock()
        message = {
            "1": {
                "2": "chat-id@goofish",
                "5": 0,
                "10": {
                    "senderNick": "buyer",
                    "senderUserId": "buyer-id",
                    "reminderContent": "你好",
                },
            }
        }
        encoded = base64.b64encode(json.dumps(message).encode()).decode()
        message_data = {
            "body": {"syncPushPackage": {"data": [{"data": encoded}]}}
        }
        fake_db = Mock()
        fake_db.matches_message_filter.return_value = None

        with patch("app.db_manager.db_manager", fake_db):
            await live.handle_message(message_data, Mock())

        live._extract_order_id.assert_not_called()
        live.fetch_order_real_values.assert_not_called()
        live.fetch_order_detail_info.assert_not_called()
        live._schedule_debounced_reply.assert_awaited_once()

    async def test_manual_chat_send_remains_available_when_auto_reply_is_disabled(self):
        account = Mock()
        account.send_im_text = AsyncMock(return_value={"body": {"messageId": "manual-1"}})

        async def run_on_account_loop(cookie_id, operation):
            self.assertEqual(cookie_id, "runtime-gate-test")
            return await operation(account)

        with (
            patch.object(reply_server, "_get_owned_chat_account"),
            patch.object(reply_server, "_run_on_account_loop", side_effect=run_on_account_loop),
        ):
            response = await reply_server.send_chat_message(
                "runtime-gate-test",
                reply_server.ChatSendMessageRequest(
                    cid="chat-id",
                    to_user_id="buyer-id",
                    text="你好，人工回复",
                ),
                {"user_id": 1, "username": "admin"},
            )

        self.assertEqual(response["data"]["messageId"], "manual-1")
        account.send_im_text.assert_awaited_once_with(
            "chat-id", "buyer-id", "你好，人工回复"
        )

    async def test_periodic_token_refresh_is_not_called_when_feature_is_disabled(self):
        live = object.__new__(XianyuLive)
        live.cookie_id = "token-gate-test"
        live.is_feature_enabled = Mock(return_value=False)
        live.refresh_token = AsyncMock()

        with patch("app.cookie_manager.manager", None):
            await live.token_refresh_loop()

        live.refresh_token.assert_not_awaited()

    async def test_enabled_periodic_refresh_still_runs_once(self):
        live = object.__new__(XianyuLive)
        live.cookie_id = "token-gate-test"
        live.is_feature_enabled = Mock(return_value=True)
        live.last_token_refresh_time = 0
        live.token_refresh_interval = 1
        live.ws = type("ClosedSocket", (), {"closed": True})()
        live.refresh_token = AsyncMock(return_value="new-token")
        live.send_token_refresh_notification = AsyncMock()
        live._interruptible_sleep = AsyncMock()

        with patch("app.cookie_manager.manager", None):
            await live.token_refresh_loop()

        live.refresh_token.assert_awaited_once()

    async def test_initial_connection_refresh_remains_available_when_periodic_refresh_is_disabled(self):
        live = object.__new__(XianyuLive)
        live.cookie_id = "initial-token-test"
        live.current_token = None
        live.last_token_refresh_time = time.time()
        live.token_refresh_interval = 3600
        live.device_id = "device-id"
        live.refresh_token = AsyncMock()

        async def issue_initial_token():
            live.current_token = "initial-token"
            return live.current_token

        live.refresh_token.side_effect = issue_initial_token
        ws = AsyncMock()
        with patch("XianyuAutoAsync.asyncio.sleep", new=AsyncMock()):
            await live.init(ws)

        live.refresh_token.assert_awaited_once()
        self.assertEqual(ws.send.await_count, 2)


if __name__ == "__main__":
    unittest.main()
