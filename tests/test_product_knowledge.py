"""商品知识库的阶段性合同测试。

这些测试先于生产实现加入。旧实现仍可导入测试模块，但会因为缺少知识
数据库/服务合同而产生语义失败；这样不会把 ImportError 当成红灯证据。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db_manager import DBManager

try:
    from app.product_knowledge import (
        COMMERCIAL_SENSITIVE_REPLY,
        SAFETY_REPLY,
        KnowledgeVersionConflict,
        ProductKnowledgeService,
    )
    _KNOWLEDGE_IMPORT_ERROR = None
except ImportError as exc:  # 旧实现的语义红灯由 availability 用例报告
    COMMERCIAL_SENSITIVE_REPLY = "这个问题涉及内部信息，暂不提供。"
    SAFETY_REPLY = "目前没有收到玩家反馈有封号情况出现。"
    KnowledgeVersionConflict = RuntimeError
    ProductKnowledgeService = None
    _KNOWLEDGE_IMPORT_ERROR = exc


def _entry(key="install.launcher", answer="请使用正式包中的 Launcher.exe 启动。", **overrides):
    value = {
        "knowledge_key": key,
        "category": "install",
        "question_patterns": ["怎么安装", "如何启动"],
        "keywords": ["安装", "启动", "Launcher.exe"],
        "answer": answer,
        "source_refs": ["README.md：安装说明"],
        "priority": 10,
        "enabled": True,
    }
    value.update(overrides)
    return value


class ProductKnowledgeAvailabilityTests(unittest.TestCase):
    def test_product_knowledge_module_is_available(self):
        self.assertIsNone(
            _KNOWLEDGE_IMPORT_ERROR,
            f"商品知识服务尚未实现，不能以导入错误作为完成证据: {_KNOWLEDGE_IMPORT_ERROR}",
        )
        self.assertIsNotNone(ProductKnowledgeService)


class ProductKnowledgeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DBManager(str(Path(self.temp_dir.name) / "knowledge.db"))

    def tearDown(self):
        if getattr(self.db, "conn", None):
            self.db.conn.close()
            self.db.conn = None
        self.temp_dir.cleanup()

    def _require_db_contract(self):
        required = (
            "get_product_knowledge_document",
            "list_product_knowledge_entries",
            "replace_product_knowledge",
            "delete_product_knowledge_for_item",
        )
        missing = [name for name in required if not hasattr(self.db, name)]
        self.assertFalse(missing, f"知识库 DB 合同缺少: {missing}")

    def _replace(self, cookie_id="account-a", item_id="item-1", expected_version=0, entries=None):
        self._require_db_contract()
        return self.db.replace_product_knowledge(
            cookie_id,
            item_id,
            product_key="passistant",
            display_name="Passistant 知识库",
            entries=list(entries if entries is not None else [_entry()]),
            expected_version=expected_version,
            seed_version="test-seed-v1",
            checksum="test-checksum",
        )

    def test_schema_has_document_and_entry_tables(self):
        tables = {
            row[0]
            for row in self.db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("ai_product_knowledge_documents", tables)
        self.assertIn("ai_product_knowledge_entries", tables)

    def test_missing_document_returns_version_zero(self):
        self._require_db_contract()
        document = self.db.get_product_knowledge_document("account-a", "item-1")
        self.assertEqual(document["version"], 0)
        self.assertEqual(document["entry_count"], 0)

    def test_replace_is_atomic_and_increments_version(self):
        document = self._replace()
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["entry_count"], 1)
        rows = self.db.list_product_knowledge_entries("account-a", "item-1")
        self.assertEqual(rows[0]["knowledge_key"], "install.launcher")

    def test_stale_version_raises_without_changing_rows(self):
        self._replace()
        with self.assertRaises(KnowledgeVersionConflict):
            self._replace(expected_version=0, entries=[_entry(key="other")])
        document = self.db.get_product_knowledge_document("account-a", "item-1")
        rows = self.db.list_product_knowledge_entries("account-a", "item-1")
        self.assertEqual(document["version"], 1)
        self.assertEqual([row["knowledge_key"] for row in rows], ["install.launcher"])

    def test_empty_replace_keeps_document_version(self):
        self._replace()
        document = self._replace(expected_version=1, entries=[])
        self.assertEqual(document["version"], 2)
        self.assertEqual(document["entry_count"], 0)
        self.assertEqual(self.db.list_product_knowledge_entries("account-a", "item-1"), [])

    def test_cookie_and_item_scopes_do_not_cross_read(self):
        self._replace("account-a", "item-1")
        self._replace("account-a", "item-2", entries=[_entry(key="second")])
        self._replace("account-b", "item-1", entries=[_entry(key="other-account")])
        self.assertEqual(
            [row["knowledge_key"] for row in self.db.list_product_knowledge_entries("account-a", "item-1")],
            ["install.launcher"],
        )
        self.assertEqual(
            [row["knowledge_key"] for row in self.db.list_product_knowledge_entries("account-a", "item-2")],
            ["second"],
        )
        self.assertEqual(
            [row["knowledge_key"] for row in self.db.list_product_knowledge_entries("account-b", "item-1")],
            ["other-account"],
        )

    def test_delete_scope_removes_knowledge_only_for_target(self):
        self._replace("account-a", "item-1")
        self._replace("account-a", "item-2", entries=[_entry(key="second")])
        self.assertTrue(self.db.delete_product_knowledge_for_item("account-a", "item-1"))
        self.assertEqual(self.db.get_product_knowledge_document("account-a", "item-1")["version"], 0)
        self.assertEqual(self.db.get_product_knowledge_document("account-a", "item-2")["version"], 1)


class ProductKnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DBManager(str(Path(self.temp_dir.name) / "knowledge.db"))
        if ProductKnowledgeService is None:
            self.skipTest("商品知识服务尚未实现；由 availability 用例记录语义红灯")
        self.service = ProductKnowledgeService(self.db)
        self.db.replace_product_knowledge(
            "account-a",
            "item-1",
            product_key="passistant",
            display_name="Passistant 知识库",
            entries=[
                _entry(
                    key="pricing.current-promotion",
                    category="pricing",
                    question_patterns=["多少钱一个月"],
                    keywords=["价格", "9.9", "29.9"],
                    answer="原价29.9元/月，当前活动口径3折，活动价9.9元/月。",
                    priority=100,
                ),
                _entry(
                    key="install.launcher",
                    answer="请使用 Launcher.exe 启动。",
                    priority=10,
                ),
            ],
            expected_version=0,
            seed_version="test-seed-v1",
            checksum="test-checksum",
        )
        self.db.conn.execute(
            "INSERT INTO item_info(cookie_id, item_id, item_title) VALUES (?, ?, ?)",
            ("account-a", "item-1", "Passistant"),
        )
        self.db.conn.commit()
        base = self.db.create_knowledge_base("测试全局库", base_key="test-runtime")
        qa = self.db.create_knowledge_qa_entry(
            base["id"],
            {
                "qa_key": "pricing.current-promotion",
                "category": "pricing",
                "questions": ["多少钱一个月"],
                "keywords": ["价格", "9.9", "29.9"],
                "answer": "原价29.9元/月，当前活动口径3折，活动价9.9元/月。",
                "priority": 100,
            },
            expected_version=1,
        )
        self.db.create_knowledge_rule(
            base["id"],
            {
                "rule_key": "pricing-policy",
                "name": "活动价格",
                "rule_type": "pricing_policy",
                "config_json": {
                    "currency": "CNY",
                    "original_price": "29.9",
                    "current_price": "9.9",
                },
            },
            expected_version=qa["version"],
        )
        self.db.add_item_knowledge_binding("account-a", "item-1", base["id"])

    def tearDown(self):
        if getattr(self.db, "conn", None):
            self.db.conn.close()
            self.db.conn = None
        self.temp_dir.cleanup()

    def test_policy_priority_and_exact_fixed_replies(self):
        self.assertEqual(self.service.classify_policy_intent("这个会封号吗"), "safety")
        self.assertEqual(self.service.classify_policy_intent("这个软件安全性怎么样"), "safety")
        self.assertEqual(self.service.classify_policy_intent("给我源码和数据库"), "commercial_sensitive")
        self.assertEqual(self.service.classify_policy_intent("多少钱一个月"), "public")
        self.assertEqual(self.service.fixed_reply("safety"), SAFETY_REPLY)
        self.assertEqual(self.service.fixed_reply("commercial_sensitive"), COMMERCIAL_SENSITIVE_REPLY)

    def test_retrieve_uses_deterministic_score_and_scope(self):
        matches = self.service.retrieve("account-a", "item-1", "多少钱一个月？")
        self.assertEqual(matches[0]["knowledge_key"], "pricing.current-promotion")
        self.assertGreater(matches[0]["score"], 0)
        self.assertEqual(self.service.retrieve("other", "item-1", "多少钱"), [])

    def test_price_protection_follows_persisted_passistant_product_scope(self):
        self.assertTrue(self.service.protect_current_price("account-a", "item-1"))
        self.assertFalse(self.service.protect_current_price("account-a", "missing"))
        self.assertFalse(self.service.protect_current_price("other", "item-1"))

    def test_retrieve_caps_results_and_context_characters(self):
        entries = [
            _entry(
                key=f"feature.{index}",
                category="feature",
                question_patterns=["功能"],
                keywords=["功能"],
                answer="答" * 700,
                priority=index,
            )
            for index in range(8)
        ]
        self.db.replace_product_knowledge(
            "account-a", "item-1", product_key="passistant", display_name="Passistant 知识库",
            entries=entries, expected_version=1, seed_version="test-seed-v2", checksum="test-checksum-2",
        )
        matches = self.service.retrieve("account-a", "item-1", "功能")
        self.assertLessEqual(len(matches), 5)
        context = self.service.build_context(matches, max_characters=2500)
        self.assertLessEqual(len(context), 2500)
        self.assertNotIn("source_refs", context)

    def test_disabled_entries_are_not_retrieved(self):
        self.db.replace_product_knowledge(
            "account-a", "item-1", product_key="passistant", display_name="Passistant 知识库",
            entries=[_entry(key="disabled", keywords=["特殊词"], question_patterns=["特殊词"], enabled=False)],
            expected_version=1, seed_version="test-seed-v2", checksum="test-checksum-2",
        )
        self.assertEqual(self.service.retrieve("account-a", "item-1", "特殊词"), [])

    def test_seed_is_valid_json_with_stable_checksum(self):
        seed_path = Path(__file__).parents[1] / "app" / "knowledge" / "passistant_public_v1.json"
        self.assertTrue(seed_path.exists(), "Passistant 公共 seed 尚未加入")
        parsed = json.loads(seed_path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["product_key"], "passistant")
        self.assertEqual(parsed["display_name"], "Passistant 知识库")
        self.assertIsInstance(parsed["entries"], list)
        checksum = self.service.seed_checksum(parsed)
        self.assertEqual(len(checksum), 64)
        self.assertEqual(checksum, self.service.seed_checksum(parsed))

    def test_seed_contains_authoritative_follow_and_multi_open_limits(self):
        seed_path = Path(__file__).parents[1] / "app" / "knowledge" / "passistant_public_v1.json"
        parsed = json.loads(seed_path.read_text(encoding="utf-8"))
        entries = {entry["knowledge_key"]: entry for entry in parsed["entries"]}

        self.assertEqual(
            entries["feature.follower"]["answer"],
            "支持队伍跟随，但只能前台跟随：跟随的目标游戏角色所在的游戏窗口必须保持在前台。一次只能有一个窗口跟随，多开时请轮流操作。",
        )
        self.assertEqual(
            entries["feature.multi-launch"]["answer"],
            "支持多开。使用跟随功能时，一次只能有一个窗口跟随，请在多个窗口之间轮流操作。",
        )
        self.assertEqual(
            entries["limitation.follower-foreground"]["answer"],
            "跟随只能前台进行，跟随的目标游戏角色所在的游戏窗口必须保持在前台。若想实现后台跟随，只能自行在虚拟机中启动游戏，并让虚拟机里的游戏角色开启软件跟随功能；也可以使用多台电脑，每台电脑启动一个游戏账号和软件。虚拟机的使用方法本店不提供。",
        )

    def test_seed_how_to_answer_recommends_official_trial(self):
        seed_path = Path(__file__).parents[1] / "app" / "knowledge" / "passistant_public_v1.json"
        parsed = json.loads(seed_path.read_text(encoding="utf-8"))
        entry = next(item for item in parsed["entries"] if item["knowledge_key"] == "install.runtime")

        self.assertIn("怎么用", entry["question_patterns"])
        self.assertIn("官网下载", entry["answer"])
        self.assertIn("注册账号", entry["answer"])
        self.assertIn("每个账号有 5 分钟试用时间", entry["answer"])
        self.assertIn("重新注册账号", entry["answer"])
        self.assertIn("仍可获得 5 分钟试用时间", entry["answer"])

    def test_documented_entry_boundaries_are_accepted(self):
        entry = _entry(
            key="a",
            answer="答" * 800,
            question_patterns=[f"问题{index}" for index in range(20)],
            keywords=[f"词{index}" for index in range(30)],
        )
        validated = self.service.validate_entries([entry], require_sources=True)
        self.assertEqual(validated[0]["knowledge_key"], "a")
        self.assertEqual(len(validated[0]["answer"]), 800)
        self.assertEqual(len(validated[0]["question_patterns"]), 20)
        self.assertEqual(len(validated[0]["keywords"]), 30)

    def test_entry_values_are_trimmed_and_deduplicated_in_first_seen_order(self):
        entry = _entry(
            question_patterns=[" 怎么安装 ", "怎么安装", "如何启动"],
            keywords=[" 安装 ", "安装", "启动"],
            source_refs=[" README.md ", "README.md", "指南.md"],
        )
        validated = self.service.validate_entries([entry], require_sources=True)[0]
        self.assertEqual(validated["question_patterns"], ["怎么安装", "如何启动"])
        self.assertEqual(validated["keywords"], ["安装", "启动"])
        self.assertEqual(validated["source_refs"], ["README.md", "指南.md"])

    def test_documented_entry_boundaries_are_rejected(self):
        invalid_entries = (
            _entry(key="a" * 81),
            _entry(answer="答" * 801),
            _entry(question_patterns=["问" * 81]),
            _entry(keywords=["词" * 33]),
            _entry(source_refs=["源" * 241]),
        )
        for entry in invalid_entries:
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    self.service.validate_entries([entry], require_sources=True)

    def test_knowledge_payload_is_limited_to_512_kib(self):
        entries = [
            _entry(
                key=f"feature.{index}",
                answer="答" * 800,
                question_patterns=[f"{index}-{part}-" + "问" * 70 for part in range(20)],
                keywords=[f"{index}-{part}-" + "词" * 25 for part in range(30)],
            )
            for index in range(200)
        ]
        with self.assertRaisesRegex(ValueError, "512 KiB"):
            self.service.validate_entries(entries, require_sources=True)

    def test_generic_output_validator_does_not_hardcode_passistant_pricing(self):
        matches = self.service.retrieve("account-a", "item-1", "多少钱一个月")
        validated = self.service.validate_model_reply(
            "现在9.9元30天，固定价。",
            "多少钱一个月",
            matches,
        )
        self.assertEqual(validated, "现在9.9元30天，固定价。")
        incomplete = self.service.validate_model_reply(
            "9.9元/月，自动发货。",
            "多少钱一个月",
            matches,
        )
        self.assertEqual(incomplete, "9.9元/月，自动发货。")


class _KnowledgeRouteDB:
    """只给路由测试提供账号/商品所有权视图，知识读写仍委托临时 DB。"""

    def __init__(self, inner):
        self.inner = inner

    def get_all_cookies(self, user_id):
        return {"account-a": {"id": "account-a"}} if user_id == 7 else {}

    def get_item_info(self, cookie_id, item_id):
        if cookie_id == "account-a" and item_id == "item-1":
            return {"item_id": item_id, "item_price": "9.90", "item_title": "Passistant"}
        return None

    def __getattr__(self, name):
        return getattr(self.inner, name)


class ProductKnowledgeRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inner_db = DBManager(str(Path(self.temp_dir.name) / "route.db"))
        self.route_db = _KnowledgeRouteDB(self.inner_db)
        from fastapi.testclient import TestClient
        from app import reply_server

        self.reply_server = reply_server
        self.client = TestClient(reply_server.app)
        reply_server.app.dependency_overrides[reply_server.get_current_user] = lambda: {
            "user_id": 7,
            "username": "admin",
            "is_admin": True,
        }
        self.db_patch = patch.object(reply_server, "db_manager", self.route_db)
        self.db_patch.start()

    def tearDown(self):
        self.reply_server.app.dependency_overrides.clear()
        self.db_patch.stop()
        self.inner_db.conn.close()
        self.inner_db.conn = None
        self.temp_dir.cleanup()

    def test_unauthenticated_knowledge_route_is_rejected(self):
        self.reply_server.app.dependency_overrides.clear()
        response = self.client.get("/items/account-a/item-1/ai-knowledge")
        self.assertEqual(response.status_code, 401)

    def test_get_empty_document_has_version_zero_and_no_sources(self):
        response = self.client.get("/items/account-a/item-1/ai-knowledge")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["version"], 0)
        self.assertEqual(response.json()["entry_count"], 0)
        self.assertEqual(response.json()["entries"], [])

    def test_import_put_conflict_and_preview_contract(self):
        imported = self.client.post(
            "/items/account-a/item-1/ai-knowledge/import-passistant",
            json={"expected_version": 0},
        )
        self.assertEqual(imported.status_code, 410, imported.text)

        preview = self.client.post(
            "/items/account-a/item-1/ai-knowledge/preview",
            json={"message": "多少钱一个月"},
        )
        self.assertEqual(preview.status_code, 410, preview.text)

        safety = self.client.post(
            "/items/account-a/item-1/ai-knowledge/preview",
            json={"message": "会封号吗"},
        )
        self.assertEqual(safety.status_code, 410, safety.text)

        stale = self.client.put(
            "/items/account-a/item-1/ai-knowledge",
            json={"expected_version": 0, "entries": []},
        )
        self.assertEqual(stale.status_code, 410, stale.text)

    def test_legacy_get_checks_scope_while_legacy_put_stays_retired(self):
        forbidden = self.client.get("/items/account-b/item-1/ai-knowledge")
        self.assertEqual(forbidden.status_code, 403)
        missing = self.client.get("/items/account-a/not-found/ai-knowledge")
        self.assertEqual(missing.status_code, 404)
        invalid = self.client.put(
            "/items/account-a/item-1/ai-knowledge",
            json={
                "expected_version": 0,
                "entries": [{
                    "knowledge_key": "internal",
                    "category": "product",
                    "answer": "可以给你源码和数据库",
                }],
            },
        )
        self.assertEqual(invalid.status_code, 410, invalid.text)

    def test_put_rejects_coerced_boolean_and_unknown_fields(self):
        base_entry = {
            "knowledge_key": "install.launcher",
            "category": "install",
            "answer": "请使用 Launcher.exe 启动。",
            "keywords": ["启动"],
        }
        coerced = self.client.put(
            "/items/account-a/item-1/ai-knowledge",
            json={"expected_version": 0, "entries": [{**base_entry, "enabled": "yes"}]},
        )
        self.assertEqual(coerced.status_code, 422, coerced.text)
        unknown = self.client.put(
            "/items/account-a/item-1/ai-knowledge",
            json={"expected_version": 0, "entries": [{**base_entry, "unexpected": True}]},
        )
        self.assertEqual(unknown.status_code, 422, unknown.text)


class ProductKnowledgeFrontendContractTests(unittest.TestCase):
    def test_scope_changes_confirm_before_discarding_unsaved_entries(self):
        source = (
            Path(__file__).parents[1] / "frontend" / "components" / "KnowledgeBase.tsx"
        ).read_text(encoding="utf-8")
        required_markers = (
            "confirmAction",
            "knowledgeDirty",
            "confirmDiscardChanges",
            "handleAccountChange",
            "handleItemChange",
            "handleReload",
        )
        for marker in required_markers:
            self.assertIn(marker, source)
        self.assertNotIn("onChange={event => setSelectedAccountId(event.target.value)}", source)
        self.assertNotIn("onChange={event => setSelectedItemId(event.target.value)}", source)


class AIReplyTestRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inner_db = DBManager(str(Path(self.temp_dir.name) / "ai-test-route.db"))
        self.route_db = _KnowledgeRouteDB(self.inner_db)
        from fastapi.testclient import TestClient
        from types import SimpleNamespace
        from app import reply_server

        self.reply_server = reply_server
        self.client = TestClient(reply_server.app)
        reply_server.app.dependency_overrides[reply_server.get_current_user] = lambda: {
            "user_id": 7,
            "username": "admin",
            "is_admin": True,
        }
        self.db_patch = patch.object(reply_server, "db_manager", self.route_db)
        self.db_patch.start()
        self.manager_patch = patch.object(
            reply_server.cookie_manager,
            "manager",
            SimpleNamespace(cookies={"account-a": object()}),
        )
        self.manager_patch.start()
        self.settings_patch = patch.object(
            reply_server.db_manager,
            "get_ai_reply_settings",
            return_value={"ai_enabled": True, "api_key": "configured", "base_url": "https://example.invalid"},
        )
        self.settings_patch.start()
        self.enabled_patch = patch.object(reply_server.ai_reply_engine, "is_ai_enabled", return_value=True)
        self.enabled_patch.start()

    def tearDown(self):
        self.reply_server.app.dependency_overrides.clear()
        self.enabled_patch.stop()
        self.settings_patch.stop()
        self.manager_patch.stop()
        self.db_patch.stop()
        self.inner_db.conn.close()
        self.inner_db.conn = None
        self.temp_dir.cleanup()

    def test_ai_test_requires_item_id_and_uses_stored_item_facts(self):
        async def fake_reply(**kwargs):
            self.generated_kwargs = kwargs
            return "按商品说明操作即可。"

        with patch.object(self.reply_server.ai_reply_engine, "generate_reply_async", side_effect=fake_reply):
            response = self.client.post(
                "/ai-reply-test/account-a",
                json={"message": "怎么用？", "item_id": "item-1"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.generated_kwargs["item_id"], "item-1")
        self.assertEqual(self.generated_kwargs["item_info"]["title"], "Passistant")
        self.assertEqual(self.generated_kwargs["item_info"]["price"], "9.90")
        self.assertNotIn("item_title", response.json())

    def test_ai_test_rejects_unknown_item_and_client_facts(self):
        unknown = self.client.post(
            "/ai-reply-test/account-a",
            json={"message": "你好", "item_id": "missing"},
        )
        self.assertEqual(unknown.status_code, 404)
        extra = self.client.post(
            "/ai-reply-test/account-a",
            json={
                "message": "你好",
                "item_id": "item-1",
                "item_title": "客户端伪造商品",
                "item_price": 0,
            },
        )
        self.assertEqual(extra.status_code, 422)

    def test_ai_test_reports_upstream_failure_as_bad_gateway(self):
        with patch.object(
            self.reply_server.ai_reply_engine,
            "generate_reply_async",
            return_value=None,
        ):
            response = self.client.post(
                "/ai-reply-test/account-a",
                json={"message": "你好", "item_id": "item-1"},
            )

        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(
            response.json()["detail"],
            "AI 服务未返回有效回复，请检查模型地址、模型名称和 API Key",
        )


if __name__ == "__main__":
    unittest.main()
