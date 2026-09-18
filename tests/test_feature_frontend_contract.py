"""前端功能快照、镜像 registry 和 context 的静态契约。"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FEATURE_KEYS = (
    "feature_items_enabled",
    "item_sync_enabled",
    "auto_polish_enabled",
    "feature_orders_enabled",
    "order_sync_enabled",
    "delivery_timeout_alert_enabled",
    "auto_delivery_enabled",
    "feature_cards_enabled",
    "feature_buyer_interaction_enabled",
    "feature_auto_reply_enabled",
    "feature_ai_reply_enabled",
    "feature_knowledge_base_enabled",
    "feature_product_automation_enabled",
    "account_profile_auto_sync_enabled",
    "scheduled_token_refresh_enabled",
    "browser_cookie_refresh_enabled",
)


class FeatureFrontendContractTests(unittest.TestCase):
    def test_shared_types_cover_backend_snapshot(self):
        source = (FRONTEND / "types.ts").read_text(encoding="utf-8")
        self.assertIn("export type FeatureKey", source)
        self.assertIn("export interface FeatureFlagDefinition", source)
        self.assertIn("export interface FeatureFlagSnapshot", source)
        for key in FEATURE_KEYS:
            self.assertIn(key, source)

    def test_registry_has_exactly_typed_ui_mapping_without_runtime_defaults(self):
        path = FRONTEND / "lib" / "featureRegistry.ts"
        self.assertTrue(path.exists())
        source = path.read_text(encoding="utf-8")
        self.assertIn("satisfies Record<FeatureKey", source)
        self.assertNotIn("default:", source)
        for key in FEATURE_KEYS:
            self.assertIn(key, source)

    def test_api_exposes_snapshot_read_and_revision_update(self):
        source = (FRONTEND / "services" / "api.ts").read_text(encoding="utf-8")
        self.assertIn("getFeatureFlags", source)
        self.assertIn("updateFeatureFlags", source)
        self.assertIn("/feature-flags", source)
        self.assertIn("expected_revision", source)

    def test_context_loads_fail_closed_and_preserves_server_snapshot(self):
        path = FRONTEND / "contexts" / "FeatureFlagsContext.tsx"
        self.assertTrue(path.exists())
        source = path.read_text(encoding="utf-8")
        self.assertIn("createContext", source)
        self.assertIn("getFeatureFlags", source)
        self.assertIn("setSnapshot", source)
        self.assertIn("return false", source)
        self.assertIn("updateFeatureFlags", source)

    def test_settings_has_admin_only_atomic_feature_area(self):
        source = (FRONTEND / "components" / "Settings.tsx").read_text(encoding="utf-8")
        for marker in (
            "useFeatureFlags",
            "SettingsSection =",
            "features",
            "handleToggleFeature",
            "await updateFeatureFlagsState(patch)",
            "configured",
            "effective",
            "depends_on",
            "runtimeApply",
            "isAdmin",
            "disabled={!isAdmin",
        ):
            self.assertIn(marker, source)

    def test_feature_toggles_persist_immediately_and_enable_dependencies(self):
        source = (FRONTEND / "components" / "Settings.tsx").read_text(encoding="utf-8")
        for marker in (
            "handleToggleFeature",
            "await updateFeatureFlagsState(patch)",
            "definition.depends_on",
            "功能开关自动保存",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("updateFeatureFlagsState(changedFlags)", source)

    def test_app_provides_one_feature_snapshot_context_after_auth(self):
        source = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("FeatureFlagsProvider", source)
        self.assertIn("<FeatureFlagsProvider isAdmin={isAdmin}>", source)
        self.assertIn("</FeatureFlagsProvider>", source)

    def test_navigation_and_mounting_use_the_same_fail_closed_page_gate(self):
        sidebar = (FRONTEND / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
        app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
        registry = (FRONTEND / "lib" / "featureRegistry.ts").read_text(encoding="utf-8")
        self.assertIn("useFeatureFlags", sidebar)
        self.assertIn("isFeaturePageEnabled", sidebar)
        self.assertIn(".filter", sidebar)
        self.assertIn("isFeaturePageEnabled", app)
        self.assertIn("activeTab === 'dashboard'", app)
        self.assertIn("snapshot: featureSnapshot, loading: featureFlagsLoading", app)
        self.assertIn("if (active && !featureFlagsLoading && !enabled)", app)
        self.assertNotIn("hidden={activeTab", app)
        self.assertIn("'notifications'", registry)

    def test_local_actions_share_feature_state_and_disabled_api_message(self):
        feedback = (FRONTEND / "services" / "feedback.ts").read_text(encoding="utf-8")
        item_list = (FRONTEND / "components" / "ItemList.tsx").read_text(encoding="utf-8")
        order_list = (FRONTEND / "components" / "OrderList.tsx").read_text(encoding="utf-8")
        buyer = (FRONTEND / "components" / "BuyerInteraction.tsx").read_text(encoding="utf-8")
        for source in (item_list, order_list, buyer):
            self.assertIn("useFeatureFlags", source)
            self.assertIn("isEnabled", source)
        for key in ("item_sync_enabled", "auto_polish_enabled", "auto_delivery_enabled"):
            self.assertIn(key, item_list)
        for key in ("feature_orders_enabled", "order_sync_enabled", "auto_delivery_enabled"):
            self.assertIn(key, order_list)
        self.assertIn("feature_buyer_interaction_enabled", buyer)
        self.assertIn("feature_disabled", feedback)
        self.assertIn("系统设置 > 功能区", feedback)


if __name__ == "__main__":
    unittest.main()
