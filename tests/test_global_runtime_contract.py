"""Phase 1 运行时、回复风格和前端交互红灯合同。"""

import json
import tempfile
import unittest
from pathlib import Path

from app.db_manager import DBManager
from app.product_knowledge import HUMAN_CONFIRMATION_REPLY, ProductKnowledgeService

try:
    from app.knowledge_runtime import KnowledgeRuntimeService
    _RUNTIME_IMPORT_ERROR = None
except ImportError as exc:
    KnowledgeRuntimeService = None
    _RUNTIME_IMPORT_ERROR = exc


class GlobalRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(str(Path(self.tmp.name) / "runtime.db"))
        self.db.conn.execute(
            "INSERT INTO item_info(cookie_id,item_id,item_title) VALUES (?,?,?)",
            ("cookie-a", "item-1", "普通商品"),
        )
        self.db.conn.commit()

    def tearDown(self):
        self.db.conn.close()
        self.tmp.cleanup()

    def test_runtime_service_is_binding_scoped_and_sources_are_not_context(self):
        self.assertIsNone(_RUNTIME_IMPORT_ERROR, _RUNTIME_IMPORT_ERROR)
        self.assertIsNotNone(KnowledgeRuntimeService)
        base = self.db.create_knowledge_base("运行时库", base_key="runtime")
        source = self.db.create_knowledge_source(base["id"], {"source_key": "s", "title": "来源", "reference": "审计"}, expected_version=1)
        self.db.create_knowledge_fact(base["id"], {"fact_key": "f", "category": "product", "title": "事实", "content": "只给模型的公开事实", "source_ids": [source["id"]]}, expected_version=2)
        self.db.add_item_knowledge_binding("cookie-a", "item-1", base["id"])
        snapshot = KnowledgeRuntimeService(self.db).snapshot("cookie-a", "item-1")
        self.assertTrue(snapshot["facts"])
        self.assertNotIn("source_ids", json.dumps(snapshot, ensure_ascii=False))
        self.assertEqual(KnowledgeRuntimeService(self.db).snapshot("cookie-a", "other"), {"facts": [], "qa_entries": [], "rules": []})

    def test_context_contains_only_ranked_matches_and_preserves_delimiters(self):
        matches = [
            {"qa_key": f"qa-{index}", "category": "feature", "answer": f"命中答案 {index}"}
            for index in range(7)
        ]
        context = KnowledgeRuntimeService.build_context(matches, max_characters=120)
        self.assertIn("命中答案 0", context)
        self.assertNotIn("命中答案 6", context)
        self.assertTrue(context.endswith("</public_product_knowledge>"))
        self.assertLessEqual(len(context), 120)

    def test_buyer_visible_fact_can_be_matched_by_title(self):
        base = self.db.create_knowledge_base("事实库", base_key="fact-search")
        self.db.create_knowledge_fact(base["id"], {
            "fact_key": "warranty.period",
            "category": "service",
            "title": "保修期限",
            "content": "本商品提供三十天售后支持。",
        }, expected_version=1)
        self.db.add_item_knowledge_binding("cookie-a", "item-1", base["id"])

        matches = KnowledgeRuntimeService(self.db).match("cookie-a", "item-1", "保修期限多久")["matches"]
        self.assertEqual(matches[0]["fact_key"], "warranty.period")

    def test_equal_matches_follow_binding_sort_order_before_base_key(self):
        first = self.db.create_knowledge_base("先绑定", base_key="z-first")
        second = self.db.create_knowledge_base("后绑定", base_key="a-second")
        for base, key, answer in ((first, "first", "先绑定答案"), (second, "second", "后绑定答案")):
            self.db.create_knowledge_qa_entry(base["id"], {
                "qa_key": key,
                "questions": ["同一个问题"],
                "answer": answer,
            }, expected_version=1)
        self.db.add_item_knowledge_binding("cookie-a", "item-1", first["id"])
        self.db.add_item_knowledge_binding("cookie-a", "item-1", second["id"])

        matches = KnowledgeRuntimeService(self.db).match("cookie-a", "item-1", "同一个问题")["matches"]
        self.assertEqual([entry["answer"] for entry in matches[:2]], ["先绑定答案", "后绑定答案"])

    def test_corrupt_rule_config_fails_closed_without_crashing_snapshot(self):
        base = self.db.create_knowledge_base("损坏规则库", base_key="corrupt-rule")
        self.db.conn.execute(
            """INSERT INTO ai_knowledge_rules(
                   id, knowledge_base_id, rule_key, name, rule_type, config_json, enabled
               ) VALUES (?, ?, ?, ?, ?, ?, 1)""",
            ("broken-rule", base["id"], "broken", "损坏规则", "pricing_policy", '"not-an-object"'),
        )
        self.db.conn.commit()
        self.db.add_item_knowledge_binding("cookie-a", "item-1", base["id"])

        snapshot = KnowledgeRuntimeService(self.db).snapshot("cookie-a", "item-1")
        self.assertEqual(snapshot["rules"], [])
        self.assertTrue(snapshot["rules_corrupt"])

    def test_normalization_uses_nfkc_and_casefold(self):
        self.assertEqual(KnowledgeRuntimeService._text("  ＰＡＳＳＩＳＴＡＮＴ  "), "passistant")

    def test_fixed_rule_respects_all_match_mode(self):
        base = self.db.create_knowledge_base("组合匹配库", base_key="match-all")
        self.db.create_knowledge_rule(base["id"], {
            "rule_key": "both-terms",
            "name": "同时命中",
            "rule_type": "fixed_reply",
            "matchers": ["源码", "偏移"],
            "response": "不提供内部信息。",
            "config_json": {"match_mode": "all"},
        }, expected_version=1)
        self.db.add_item_knowledge_binding("cookie-a", "item-1", base["id"])
        runtime = KnowledgeRuntimeService(self.db)

        self.assertIsNone(runtime.match("cookie-a", "item-1", "能给源码吗")["fixed_reply"])
        self.assertEqual(
            runtime.match("cookie-a", "item-1", "能给源码和偏移吗")["fixed_reply"],
            "不提供内部信息。",
        )

    def test_passistant_trial_rule_answers_only_trial_questions(self):
        self.db.conn.execute(
            "INSERT INTO item_info(cookie_id,item_id,item_title) VALUES (?,?,?)",
            ("cookie-a", "1081710901648", "流放之路2 Passistant"),
        )
        self.db.conn.commit()
        base = self.db.list_knowledge_bases()[0]
        runtime = KnowledgeRuntimeService(self.db)

        self.assertIn("5 分钟", runtime.match("cookie-a", "1081710901648", "试用期多久")["fixed_reply"])
        self.assertIn("重新注册", runtime.match("cookie-a", "1081710901648", "试用不够怎么办")["fixed_reply"])
        self.assertIsNone(runtime.match("cookie-a", "item-1", "试用期多久")["fixed_reply"])

    def test_legacy_rule_config_is_normalized_for_editing_and_runtime(self):
        base = self.db.create_knowledge_base("旧规则库", base_key="legacy-rule")
        self.db.conn.execute(
            """INSERT INTO ai_knowledge_rules(
                   id, knowledge_base_id, rule_key, name, rule_type, matchers, config_json, enabled
               ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                "legacy-output", base["id"], "legacy-output", "旧输出保护", "output_guard",
                json.dumps(["安全", "封号"], ensure_ascii=False),
                json.dumps({"only_when_asked": True}, ensure_ascii=False),
            ),
        )
        self.db.conn.commit()

        rule = self.db.get_knowledge_base(base["id"])["rules"][0]
        self.assertNotIn("only_when_asked", rule["config_json"])
        self.assertEqual(rule["config_json"]["forbidden_unless_asked"], ["安全", "封号"])
        self.assertEqual(rule["config_json"]["fallback_mode"], "human_confirmation")

    def test_legacy_product_rows_are_never_a_runtime_fallback(self):
        self.db.replace_product_knowledge(
            "cookie-a",
            "item-1",
            product_key="passistant",
            display_name="Passistant 知识库",
            entries=[{
                "knowledge_key": "legacy",
                "category": "pricing",
                "question_patterns": ["多少钱"],
                "keywords": ["价格"],
                "answer": "旧 Passistant 价格",
                "source_refs": [],
                "priority": 1,
                "enabled": True,
            }],
            expected_version=0,
        )
        service = ProductKnowledgeService(self.db)
        self.assertEqual(service.retrieve("cookie-a", "item-1", "多少钱"), [])
        self.assertFalse(service.protect_current_price("cookie-a", "item-1"))

    def test_generic_output_validation_does_not_apply_passistant_terms(self):
        service = ProductKnowledgeService(self.db)
        self.assertEqual(
            service.validate_model_reply("这个普通商品使用起来很安全。", "怎么使用", []),
            "这个普通商品使用起来很安全。",
        )
        self.assertEqual(
            service.validate_model_reply("路径是 C:\\secret\\config.json", "配置在哪", []),
            HUMAN_CONFIRMATION_REPLY,
        )

    def test_bound_output_guard_only_blocks_unasked_terms(self):
        rules = [{
            "rule_type": "output_guard",
            "matchers": ["安全", "封号"],
            "config_json": {
                "forbidden_unless_asked": ["安全", "封号"],
                "fallback_mode": "human_confirmation",
            },
        }]
        from app.ai_reply_engine import AIReplyEngine

        self.assertEqual(
            AIReplyEngine._apply_bound_output_guard("安装简单而且很安全。", "怎么安装", rules),
            HUMAN_CONFIRMATION_REPLY,
        )
        self.assertEqual(
            AIReplyEngine._apply_bound_output_guard("目前使用很安全。", "安全吗", rules),
            "目前使用很安全。",
        )


class ReplyStyleAndFrontendContractTests(unittest.TestCase):
    ROOT = Path(__file__).parents[1]

    def test_style_default_has_no_product_business_terms(self):
        style = DBManager(":memory:").get_ai_reply_profile()["reply_style"]
        for term in ("9.9", "29.9", "Passistant", "国服", "砍价", "发货", "封号"):
            self.assertNotIn(term.lower(), style.lower())

    def test_two_level_knowledge_ui_and_style_ui_contract(self):
        knowledge = (self.ROOT / "frontend/components/KnowledgeBase.tsx").read_text(encoding="utf-8")
        ai_reply = (self.ROOT / "frontend/components/AIReply.tsx").read_text(encoding="utf-8")
        account = (self.ROOT / "frontend/components/AccountList.tsx").read_text(encoding="utf-8")
        for marker in ("当前项目知识库", "全部知识库", "添加知识库", "删除知识库", "买家可见事实", "来源引用", "内部规则", "公开问答"):
            self.assertIn(marker, knowledge)
        self.assertNotIn("当前知识项目", knowledge)
        self.assertIn("全局回复风格", ai_reply)
        self.assertNotIn("custom_prompts", ai_reply)
        self.assertNotIn("max_discount_percent", ai_reply)
        self.assertNotIn("custom_prompts", account)

    def test_knowledge_editor_has_scoped_ai_question_and_server_generated_qa_keys(self):
        knowledge = (self.ROOT / "frontend/components/KnowledgeBase.tsx").read_text(encoding="utf-8")
        editor = (self.ROOT / "frontend/components/KnowledgeBaseEditorModal.tsx").read_text(encoding="utf-8")
        api = (self.ROOT / "frontend/services/api.ts").read_text(encoding="utf-8")

        self.assertIn("aiConfigAccountId={selectedAccountId}", knowledge)
        self.assertIn("知识库问答", editor)
        self.assertIn("公开问答和内部规则", editor)
        self.assertIn("askKnowledgeBase", editor)
        self.assertIn("askKnowledgeBase", api)
        self.assertIn("留空后由系统自动生成", editor)

    def test_binding_dialog_explains_when_all_knowledge_bases_are_already_attached(self):
        knowledge = (self.ROOT / "frontend/components/KnowledgeBase.tsx").read_text(encoding="utf-8")

        self.assertIn("currentProjectKnowledgeTitle", knowledge)
        self.assertIn("availableBaseCount", knowledge)
        self.assertIn("添加到当前商品", knowledge)
        self.assertIn("已添加到当前商品", knowledge)
        self.assertIn("当前商品已经添加了全部知识库，不能重复添加", knowledge)
        self.assertIn("新建知识库", knowledge)

    def test_editor_preserves_dirty_state_and_refreshes_parent_summary(self):
        knowledge = (self.ROOT / "frontend/components/KnowledgeBase.tsx").read_text(encoding="utf-8")
        editor = (self.ROOT / "frontend/components/KnowledgeBaseEditorModal.tsx").read_text(encoding="utf-8")
        self.assertIn("onDirtyChange={setKnowledgeDirty}", knowledge)
        self.assertNotIn('role="button"', knowledge)
        self.assertIn("metaDirty", editor)
        self.assertIn("contentDirty", editor)
        self.assertIn("requestTabChange", editor)
        self.assertGreaterEqual(editor.count("onSaved?.()"), 3)


if __name__ == "__main__":
    unittest.main()
