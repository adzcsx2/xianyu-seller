import asyncio
import os
import unittest
from unittest.mock import Mock, patch

import app.ai_reply_engine as ai_reply_module
from app.ai_reply_engine import AIReplyEngine
from app.reply_server import _public_ai_reply_settings


class AIReplyEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = AIReplyEngine()

    def test_plain_text_custom_prompt_is_supported(self):
        prompt = self.engine._resolve_system_prompt("不要承诺库存，回复保持简短。", "default")

        self.assertIn("不要承诺库存", prompt)
        self.assertIn("资深电商卖家", prompt)

    def test_reply_is_normalized_and_limited(self):
        reply = self.engine._normalize_reply('  "你好，   现货可拍。"  ')
        long_reply = self.engine._normalize_reply("答" * 500)

        self.assertEqual(reply, "你好， 现货可拍。")
        self.assertEqual(len(long_reply), 300)

    def test_knowledge_base_answer_uses_enabled_public_content_and_internal_guidance(self):
        settings = {
            "ai_enabled": True,
            "model_name": "deepseek-chat",
            "api_key": "test-secret",
            "base_url": "https://api.deepseek.invalid/v1",
        }
        knowledge_base = {
            "id": "base-current",
            "name": "当前知识库",
            "facts": [
                {"title": "启动方式", "content": "使用 Launcher.exe 启动。", "enabled": True, "priority": 10},
                {"title": "旧内容", "content": "不要发送的停用事实", "enabled": False, "priority": 99},
            ],
            "qa_entries": [
                {"questions": ["怎么启动"], "answer": "双击启动器。", "enabled": True, "priority": 5},
                {"questions": ["停用问答"], "answer": "不要发送的停用答案", "enabled": False, "priority": 20},
            ],
            "rules": [
                {"rule_type": "model_instruction", "instruction": "回答保持简短。", "enabled": True, "priority": 1},
                {
                    "rule_type": "pricing_policy",
                    "name": "当前活动价",
                    "intent": "pricing",
                    "config_json": {"current_price": "9.9", "currency": "CNY"},
                    "enabled": True,
                    "priority": 2,
                },
                {
                    "rule_type": "fixed_reply",
                    "response": "不要发送的停用规则",
                    "enabled": False,
                    "priority": 99,
                },
            ],
            "sources": [
                {"title": "内部来源", "notes": "不得发送给模型的内部备注"},
            ],
        }

        with (
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
            patch.object(self.engine, "_generate_with_retry", return_value="请双击 Launcher.exe 启动。") as generate,
        ):
            answer = self.engine.answer_knowledge_base(
                "account-1", knowledge_base, "这个工具怎么启动？"
            )

        self.assertEqual(answer, "请双击 Launcher.exe 启动。")
        messages = generate.call_args.args[1]
        system_text = messages[0]["content"]
        self.assertIn("当前知识库", system_text)
        self.assertIn("Launcher.exe", system_text)
        self.assertIn("双击启动器", system_text)
        self.assertIn("回答保持简短", system_text)
        self.assertIn("pricing_policy", system_text)
        self.assertIn('"current_price":"9.9"', system_text)
        self.assertNotIn("不要发送的停用事实", system_text)
        self.assertNotIn("不要发送的停用答案", system_text)
        self.assertNotIn("不要发送的停用规则", system_text)
        self.assertNotIn("不得发送给模型的内部备注", system_text)
        self.assertNotIn("source_ids", system_text)
        self.assertEqual(messages[-1], {"role": "user", "content": "这个工具怎么启动？"})

    def test_knowledge_base_answer_validates_ai_configuration_and_result(self):
        complete = {
            "ai_enabled": True,
            "model_name": "deepseek-chat",
            "api_key": "test-secret",
            "base_url": "https://api.deepseek.invalid/v1",
        }
        cases = (
            ({**complete, "ai_enabled": False}, "尚未启用"),
            ({**complete, "api_key": ""}, "API Key"),
            ({**complete, "model_name": ""}, "未配置完整"),
            ({**complete, "base_url": ""}, "未配置完整"),
        )
        for settings, expected in cases:
            with self.subTest(expected=expected), patch(
                "app.ai_reply_engine.db_manager.get_ai_reply_settings",
                return_value=settings,
            ):
                with self.assertRaisesRegex(ValueError, expected):
                    self.engine.answer_knowledge_base("account-1", {}, "测试问题")

        with self.assertRaisesRegex(ValueError, "问题不能为空"):
            self.engine.answer_knowledge_base("account-1", {}, "   ")
        with (
            patch(
                "app.ai_reply_engine.db_manager.get_ai_reply_settings",
                return_value=complete,
            ),
            patch.object(self.engine, "_generate_with_retry", return_value="  "),
        ):
            with self.assertRaisesRegex(RuntimeError, "未返回可用答案"):
                self.engine.answer_knowledge_base("account-1", {}, "测试问题")

    def test_provided_entries_match_the_prompt_character_budget(self):
        knowledge_base = {
            "facts": [
                {"fact_key": "first", "content": "甲" * 6000, "enabled": True, "priority": 2},
                {"fact_key": "second", "content": "乙" * 6000, "enabled": True, "priority": 1},
            ],
            "qa_entries": [],
        }

        selected = self.engine.knowledge_base_provided_entries(knowledge_base)
        prompt = self.engine._knowledge_base_qa_prompt(knowledge_base)

        self.assertEqual([entry["fact_key"] for entry in selected], ["first"])
        self.assertIn("甲" * 100, prompt)
        self.assertNotIn("乙" * 100, prompt)

    def test_knowledge_base_answer_preserves_multiline_content_beyond_buyer_reply_limit(self):
        settings = {
            "ai_enabled": True,
            "model_name": "deepseek-chat",
            "api_key": "test-secret",
            "base_url": "https://api.deepseek.invalid/v1",
        }
        model_answer = "第一步：下载安装包。\n\n第二步：完成配置。\n" + "补充说明。" * 80

        with (
            patch(
                "app.ai_reply_engine.db_manager.get_ai_reply_settings",
                return_value=settings,
            ),
            patch.object(
                self.engine,
                "_generate_with_retry",
                return_value=model_answer,
            ),
        ):
            answer = self.engine.answer_knowledge_base(
                "account-1", {"name": "测试知识库"}, "请给我完整步骤"
            )

        self.assertGreater(len(answer), 300)
        self.assertEqual(answer, model_answer)
        self.assertIn("\n\n", answer)

    def test_knowledge_answer_sanitizer_removes_thoughts_and_rejects_reasoning_leaks(self):
        self.assertEqual(
            self.engine._normalize_knowledge_answer(
                "<think>这里是内部推理</think>\n第一段\n第二段"
            ),
            "第一段\n第二段",
        )
        self.assertIsNone(self.engine._normalize_knowledge_answer(None))
        self.assertIsNone(
            self.engine._normalize_knowledge_answer("这里包含系统提示，不应显示")
        )

    def test_knowledge_prompt_treats_internal_rules_as_answer_evidence(self):
        prompt = self.engine._knowledge_base_qa_prompt({
            "name": "价格知识库",
            "facts": [],
            "qa_entries": [],
            "rules": [{
                "rule_type": "pricing_policy",
                "name": "当前售价",
                "intent": "pricing",
                "matchers": ["多少钱"],
                "instruction": "",
                "response": "",
                "config_json": {"current_price": "9.9", "currency": "CNY"},
                "enabled": True,
                "priority": 10,
            }],
        })

        self.assertIn("仅依据 <knowledge_data> 和 <internal_rules>", prompt)
        self.assertIn("内部规则中的业务数据可以作为回答依据", prompt)
        self.assertNotIn("仅依据 <knowledge_data> 中的事实和公开问答回答", prompt)
        self.assertIn('"current_price":"9.9"', prompt)

    def test_knowledge_prompt_truncation_keeps_valid_json_boundaries(self):
        records = [{"content": "甲" * 10}, {"content": "乙" * 10}]

        encoded = self.engine._limited_json_array(records, 30)

        self.assertEqual(encoded, '[{"content":"甲甲甲甲甲甲甲甲甲甲"}]')

    def test_generate_reply_uses_model_without_logging_or_returning_empty_content(self):
        settings = {
            "ai_enabled": True,
            "model_name": "test-model",
            "api_key": "secret",
            "base_url": "https://example.invalid/v1",
            "max_discount_percent": 10,
            "max_discount_amount": 100,
            "max_bargain_rounds": 3,
            "custom_prompts": "回复保持简短。",
        }

        with (
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "detect_intent", return_value="default"),
            patch.object(
                self.engine,
                "save_conversation",
                side_effect=["2026-08-04 10:00:00", "2026-08-04 10:00:01"],
            ) as save_conversation,
            patch.object(
                self.engine,
                "_get_recent_user_messages",
                return_value=[{"content": "有货吗", "created_at": "2026-08-04 10:00:00"}],
            ),
            patch.object(self.engine, "get_conversation_context", return_value=[]),
            patch.object(self.engine, "get_bargain_count", return_value=0),
            patch.object(self.engine, "_is_dashscope_api", return_value=False),
            patch.object(self.engine, "_is_gemini_api", return_value=False),
            patch.object(self.engine, "_create_openai_client", return_value=Mock()),
            patch.object(
                self.engine,
                "_call_openai_api",
                return_value='  "有货，可以直接拍。"  ',
            ) as call_openai,
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            reply = self.engine.generate_reply(
                message="有货吗",
                item_info={"title": "测试商品", "price": 10, "desc": "测试"},
                chat_id="chat-1",
                cookie_id="account-1",
                user_id="buyer-1",
                item_id="item-1",
                skip_wait=True,
            )

        self.assertEqual(reply, "有货，可以直接拍。")
        self.assertEqual(save_conversation.call_count, 2)
        messages = call_openai.call_args.args[2]
        self.assertEqual(
            [entry["content"] for entry in messages if entry["role"] == "user"],
            ["有货吗"],
        )

    def test_context_roles_are_preserved_and_scoped_to_item(self):
        settings = {
            "ai_enabled": True,
            "model_name": "test-model",
            "api_key": "secret",
            "base_url": "https://example.invalid/v1",
            "max_discount_percent": 10,
            "max_discount_amount": 100,
            "max_bargain_rounds": 3,
            "context_enabled": True,
            "context_message_limit": 8,
            "context_expire_minutes": 60,
            "custom_prompts": "",
        }
        history = [
            {"role": "user", "content": "支持多久？"},
            {"role": "assistant", "content": "支持一周。"},
        ]

        with (
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "detect_intent", return_value="default"),
            patch.object(
                self.engine, "save_conversation",
                side_effect=["2026-08-04 10:00:00", "2026-08-04 10:00:01"],
            ),
            patch.object(
                self.engine, "_get_recent_user_messages",
                return_value=[{"content": "怎么使用？", "created_at": "2026-08-04 10:00:00"}],
            ),
            patch.object(self.engine, "get_conversation_context", return_value=history) as get_context,
            patch.object(self.engine, "get_bargain_count", return_value=0),
            patch.object(self.engine, "_is_dashscope_api", return_value=False),
            patch.object(self.engine, "_is_gemini_api", return_value=False),
            patch.object(self.engine, "_create_openai_client", return_value=Mock()),
            patch.object(self.engine, "_call_openai_api", return_value="按说明激活即可。") as call_openai,
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            self.engine.generate_reply(
                "怎么使用？", {"title": "周卡", "price": 80, "desc": "独享"},
                "chat-1", "account-1", "buyer-1", "item-9", True,
            )

        self.assertEqual(get_context.call_args.kwargs["item_id"], "item-9")
        self.assertEqual(get_context.call_args.kwargs["limit"], 8)
        self.assertEqual(get_context.call_args.kwargs["max_age_minutes"], 60)
        messages = call_openai.call_args.args[2]
        self.assertEqual(
            [(entry["role"], entry["content"]) for entry in messages[1:]],
            [
                ("user", "支持多久？"),
                ("assistant", "支持一周。"),
                ("user", "怎么使用？"),
            ],
        )

    def test_disabled_context_does_not_query_history(self):
        settings = {
            "ai_enabled": True,
            "model_name": "test-model",
            "api_key": "secret",
            "base_url": "https://example.invalid/v1",
            "max_bargain_rounds": 3,
            "context_enabled": False,
            "custom_prompts": "",
        }
        with (
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "detect_intent", return_value="default"),
            patch.object(
                self.engine, "save_conversation",
                side_effect=["2026-08-04 10:00:00", "2026-08-04 10:00:01"],
            ),
            patch.object(
                self.engine, "_get_recent_user_messages",
                return_value=[{"content": "你好", "created_at": "2026-08-04 10:00:00"}],
            ),
            patch.object(self.engine, "get_conversation_context") as get_context,
            patch.object(self.engine, "get_bargain_count", return_value=0),
            patch.object(self.engine, "_is_dashscope_api", return_value=False),
            patch.object(self.engine, "_is_gemini_api", return_value=False),
            patch.object(self.engine, "_create_openai_client", return_value=Mock()),
            patch.object(self.engine, "_call_openai_api", return_value="你好"),
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            self.engine.generate_reply("你好", {}, "chat", "account", "buyer", "item", True)
        get_context.assert_not_called()

    def test_gemini_preserves_multi_turn_roles(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "可以"}]}}]
        }
        settings = {"api_key": "secret", "model_name": "gemini-test"}
        messages = [
            {"role": "system", "content": "系统规则"},
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
            {"role": "user", "content": "第二问"},
        ]
        with patch("app.ai_reply_engine.requests.post", return_value=response) as post:
            result = self.engine._call_gemini_api(settings, messages)

        self.assertEqual(result, "可以")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            [entry["role"] for entry in payload["contents"]],
            ["user", "model", "user"],
        )
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "系统规则")

    def test_system_and_order_events_bypass_ai(self):
        for message in (
            "[我已拍下，待付款]",
            "[已付款，待发货]",
            "[退款成功，钱款已原路退返]",
            "快给ta一个评价吧~",
        ):
            self.assertTrue(self.engine.is_system_or_order_event(message))

        with (
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "save_conversation") as save,
        ):
            result = self.engine.generate_reply(
                "[已付款，待发货]", {}, "chat", "account", "buyer", "item", True
            )
        self.assertIsNone(result)
        save.assert_not_called()

    def _settings_for_policy_tests(self):
        return {
            "ai_enabled": True,
            "model_name": "test-model",
            "api_key": "secret",
            "base_url": "https://example.invalid/v1",
            "max_discount_percent": 10,
            "max_discount_amount": 100,
            "max_bargain_rounds": 3,
            "context_enabled": True,
            "context_message_limit": 8,
            "context_expire_minutes": 60,
            "custom_prompts": "",
        }

    def test_safety_policy_returns_exact_reply_without_model_call(self):
        settings = self._settings_for_policy_tests()
        runtime = Mock()
        runtime.match.return_value = {
            "snapshot": {"facts": [], "qa_entries": [], "rules": [{"intent": "safety", "response": "目前没有收到玩家反馈有封号情况出现。"}]},
            "matches": [],
            "fixed_reply": "目前没有收到玩家反馈有封号情况出现。",
        }
        with (
            patch.object(ai_reply_module, "KnowledgeRuntimeService", return_value=runtime),
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "save_conversation", side_effect=["t1", "t2"]),
            patch.object(self.engine, "_get_recent_user_messages", return_value=[]),
            patch.object(self.engine, "get_conversation_context", return_value=[]),
            patch.object(self.engine, "get_bargain_count", return_value=0),
            patch.object(self.engine, "_generate_with_retry", return_value="模型回复") as generate,
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            reply = self.engine.generate_reply(
                "这个软件安全吗？", {"title": "Passistant", "price": "9.9", "desc": ""},
                "chat-policy", "account-1", "buyer-1", "item-1", True,
            )

        self.assertEqual(reply, "目前没有收到玩家反馈有封号情况出现。")
        generate.assert_not_called()

    def test_commercial_policy_returns_fixed_reply_without_model_call(self):
        settings = self._settings_for_policy_tests()
        runtime = Mock()
        runtime.match.return_value = {
            "snapshot": {"facts": [], "qa_entries": [], "rules": [{"intent": "commercial_sensitive", "response": "这个问题涉及内部信息，暂不提供。"}]},
            "matches": [],
            "fixed_reply": "这个问题涉及内部信息，暂不提供。",
        }
        with (
            patch.object(ai_reply_module, "KnowledgeRuntimeService", return_value=runtime),
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "save_conversation", side_effect=["t1", "t2"]),
            patch.object(self.engine, "_get_recent_user_messages", return_value=[]),
            patch.object(self.engine, "get_conversation_context", return_value=[]),
            patch.object(self.engine, "get_bargain_count", return_value=0),
            patch.object(self.engine, "_generate_with_retry", return_value="源码内容") as generate,
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            reply = self.engine.generate_reply(
                "可以给我源码和偏移吗？", {"title": "Passistant", "price": "9.9", "desc": ""},
                "chat-commercial", "account-1", "buyer-1", "item-1", True,
            )

        self.assertEqual(reply, "这个问题涉及内部信息，暂不提供。")
        generate.assert_not_called()

    def test_corrupt_bound_rule_fails_closed_before_fixed_reply(self):
        settings = self._settings_for_policy_tests()
        runtime = Mock()
        runtime.match.return_value = {
            "snapshot": {
                "facts": [], "qa_entries": [],
                "rules": [{"intent": "public", "response": "不应发送的固定回复"}],
                "rules_corrupt": ["broken-rule"],
            },
            "matches": [],
            "fixed_reply": "不应发送的固定回复",
        }
        with (
            patch.object(ai_reply_module, "KnowledgeRuntimeService", return_value=runtime),
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "save_conversation", side_effect=["t1", "t2"]),
            patch.object(self.engine, "_get_recent_user_messages", return_value=[]),
            patch.object(self.engine, "_generate_with_retry", return_value="模型回复") as generate,
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            reply = self.engine.generate_reply(
                "触发规则", {"title": "普通商品", "price": "10", "desc": ""},
                "chat-corrupt", "account-1", "buyer-1", "item-1", True,
            )

        self.assertEqual(reply, ai_reply_module.HUMAN_CONFIRMATION_REPLY)
        generate.assert_not_called()

    def test_public_knowledge_is_added_to_system_message(self):
        settings = self._settings_for_policy_tests()
        match = {
            "knowledge_key": "install.launcher",
            "category": "install",
            "answer": "请使用正式包中的 Launcher.exe 启动。",
            "score": 100,
        }
        runtime = Mock()
        runtime.match.return_value = {
            "snapshot": {"facts": [], "qa_entries": [], "rules": []},
            "matches": [match],
            "fixed_reply": None,
        }
        runtime.build_context.return_value = "<public_product_knowledge>\n[install] 请使用正式包中的 Launcher.exe 启动。\n</public_product_knowledge>"
        runtime.build_instruction_context.return_value = "<internal_product_rules>\n- 仅回答当前商品业务\n</internal_product_rules>"
        with (
            patch.object(ai_reply_module, "KnowledgeRuntimeService", return_value=runtime),
            patch.object(self.engine, "is_ai_enabled", return_value=True),
            patch.object(self.engine, "detect_intent", return_value="tech"),
            patch.object(self.engine, "save_conversation", side_effect=["t1", "t2"]),
            patch.object(self.engine, "_get_recent_user_messages", return_value=[]),
            patch.object(self.engine, "get_conversation_context", return_value=[]),
            patch.object(self.engine, "get_bargain_count", return_value=0),
            patch.object(self.engine, "_generate_with_retry", return_value="按说明启动即可。") as generate,
            patch("app.ai_reply_engine.db_manager.get_ai_reply_settings", return_value=settings),
        ):
            self.engine.generate_reply(
                "怎么启动？", {"title": "Passistant", "price": "9.9", "desc": ""},
                "chat-knowledge", "account-1", "buyer-1", "item-1", True,
            )

        messages = generate.call_args.args[1]
        system_text = messages[0]["content"]
        self.assertIn("<public_product_knowledge>", system_text)
        self.assertIn("Launcher.exe", system_text)
        self.assertNotIn("source_refs", system_text)
        self.assertLess(system_text.index("<internal_product_rules>"), system_text.index("安全边界："))

    def test_public_settings_never_return_account_api_key(self):
        with patch.dict(os.environ, {"API_KEY": ""}):
            result = _public_ai_reply_settings({
                "ai_enabled": True,
                "api_key": "top-secret",
                "model_name": "test-model",
            })

        self.assertEqual(result["api_key"], "")
        self.assertTrue(result["api_key_configured"])

    def test_admin_settings_can_return_deployment_api_key(self):
        with patch.dict(os.environ, {"API_KEY": "env-key"}):
            result = _public_ai_reply_settings({
                "ai_enabled": True,
                "api_key": "env-key",
                "model_name": "test-model",
            }, reveal_api_key=True)

        self.assertEqual(result["api_key"], "env-key")
        self.assertEqual(result["api_key_source"], "env")
        self.assertTrue(result["ai_env_overrides"]["api_key"])


class AIReplyAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_wrapper_runs_sync_generation_off_event_loop(self):
        def slow_reply(*_args):
            import time
            time.sleep(0.05)
            return "完成"

        with patch.object(self.engine, "generate_reply", side_effect=slow_reply):
            marker = []
            task = asyncio.create_task(
                self.engine.generate_reply_async(
                    "消息", {}, "chat", "account", "buyer", "item", True
                )
            )
            await asyncio.sleep(0)
            marker.append("event-loop-responsive")
            result = await task

        self.assertEqual(marker, ["event-loop-responsive"])
        self.assertEqual(result, "完成")

    def setUp(self):
        self.engine = AIReplyEngine()


if __name__ == "__main__":
    unittest.main()
