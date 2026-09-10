"""系统级功能开关的唯一定义、严格解析和依赖计算中心。"""

from dataclasses import dataclass
from typing import Any, Mapping


class InvalidFeatureFlag(ValueError):
    """功能 key、值或 patch 结构不符合合同。"""

    def __init__(self, key: str | None = None, message: str | None = None):
        self.key = key
        super().__init__(message or (f"invalid feature flag: {key}" if key else "invalid feature flag patch"))


class FeatureRevisionConflict(RuntimeError):
    """客户端基于过期 revision 更新功能开关。"""

    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"feature revision conflict: expected={expected}, current={current}")


@dataclass(frozen=True)
class FeatureFlagDefinition:
    key: str
    default: bool
    group: str
    label: str
    description: str
    depends_on: tuple[str, ...] = ()
    ui_targets: tuple[str, ...] = ()
    risk_level: str = "low"


@dataclass(frozen=True)
class FeatureFlagSnapshot:
    revision: int
    configured: dict[str, bool]
    effective: dict[str, bool]
    definitions: tuple[FeatureFlagDefinition, ...]
    warnings: tuple[str, ...] = ()


class FeatureFlagRegistry:
    """不可变、有序的功能开关注册表。"""

    def __init__(self, definitions: tuple[FeatureFlagDefinition, ...]):
        self._definitions = tuple(definitions)
        self._by_key = {item.key: item for item in self._definitions}
        if len(self._by_key) != len(self._definitions):
            raise ValueError("duplicate feature flag key")
        self._topological_keys = self._validate_dependencies()

    def definitions(self) -> tuple[FeatureFlagDefinition, ...]:
        return self._definitions

    def keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self._definitions)

    def topological_keys(self) -> tuple[str, ...]:
        return self._topological_keys

    def validate_patch(self, patch: Mapping[str, Any]) -> dict[str, bool]:
        if not isinstance(patch, Mapping) or not patch:
            raise InvalidFeatureFlag(message="feature patch must not be empty")
        validated: dict[str, bool] = {}
        for key, value in patch.items():
            if key not in self._by_key or type(value) is not bool:
                raise InvalidFeatureFlag(key)
            validated[key] = value
        return validated

    def parse_database_value(self, key: str, value: Any) -> tuple[bool, str | None]:
        definition = self._by_key[key]
        normalized = str(value).strip().lower() if value is not None else ""
        if normalized in ("true", "1"):
            return True, None
        if normalized in ("false", "0"):
            return False, None
        return definition.default, f"invalid stored value for feature {key}; using compatibility default"

    def build_snapshot(
        self,
        configured: Mapping[str, bool],
        revision: int = 0,
        warnings: tuple[str, ...] = (),
    ) -> FeatureFlagSnapshot:
        effective: dict[str, bool] = {}
        for key in self._topological_keys:
            definition = self._by_key[key]
            effective[key] = bool(configured[key]) and all(
                effective[parent] for parent in definition.depends_on
            )
        return FeatureFlagSnapshot(
            revision=revision,
            configured=dict(configured),
            effective=effective,
            definitions=self._definitions,
            warnings=tuple(warnings),
        )

    def _validate_dependencies(self) -> tuple[str, ...]:
        state: dict[str, int] = {}
        result: list[str] = []

        def visit(key: str) -> None:
            marker = state.get(key, 0)
            if marker == 1:
                raise ValueError(f"feature flag dependency cycle at {key}")
            if marker == 2:
                return
            state[key] = 1
            for parent in self._by_key[key].depends_on:
                if parent not in self._by_key:
                    raise ValueError(f"unknown feature flag dependency: {parent}")
                visit(parent)
            state[key] = 2
            result.append(key)

        for item in self._definitions:
            visit(item.key)
        return tuple(result)


def _definition(
    key: str,
    default: bool,
    group: str,
    label: str,
    description: str,
    depends_on: tuple[str, ...] = (),
    ui_targets: tuple[str, ...] = (),
    risk_level: str = "low",
) -> FeatureFlagDefinition:
    return FeatureFlagDefinition(
        key=key,
        default=default,
        group=group,
        label=label,
        description=description,
        depends_on=depends_on,
        ui_targets=ui_targets,
        risk_level=risk_level,
    )


FEATURE_FLAG_REGISTRY = FeatureFlagRegistry(
    (
        _definition("feature_items_enabled", True, "page_modules", "商品模块", "启用商品管理页面和商品动作", ui_targets=("items",), risk_level="high"),
        _definition("item_sync_enabled", True, "platform_background", "商品同步", "周期同步商品数据", ("feature_items_enabled",), ("items.sync",), "medium"),
        _definition("auto_polish_enabled", False, "platform_background", "自动擦亮", "周期执行商品擦亮", ("feature_items_enabled",), ("items.polish",), "high"),
        _definition("feature_orders_enabled", True, "page_modules", "订单模块", "启用订单管理页面和订单动作", ui_targets=("orders",), risk_level="high"),
        _definition("order_sync_enabled", True, "platform_background", "订单同步", "周期同步卖家订单", ("feature_orders_enabled",), ("orders.sync",), "high"),
        _definition("delivery_timeout_alert_enabled", True, "platform_background", "发货超时提醒", "周期检查发货超时", ("feature_orders_enabled",), ("orders.timeout",), "medium"),
        _definition("auto_delivery_enabled", True, "message_actions", "自动发货", "处理付款和免拼发货动作", ("feature_items_enabled", "feature_orders_enabled"), ("items.delivery", "orders.ship"), "high"),
        _definition("feature_cards_enabled", True, "page_modules", "卡密模块", "启用卡密库存管理", ui_targets=("cards",), risk_level="medium"),
        _definition("feature_buyer_interaction_enabled", True, "message_actions", "买家互动", "启用评价、求花和确认收货致谢动作", ("feature_orders_enabled",), ("buyer-interaction",), "high"),
        _definition("feature_auto_reply_enabled", True, "message_actions", "自动回复", "启用自动回复规则和防抖回复", ui_targets=("auto-reply",), risk_level="high"),
        _definition("feature_ai_reply_enabled", True, "message_actions", "AI 回复", "启用 AI 自动回复和测试动作", ui_targets=("ai-reply",), risk_level="high"),
        _definition("feature_knowledge_base_enabled", True, "page_modules", "知识库", "启用知识库管理和绑定", ui_targets=("knowledge-base",), risk_level="medium"),
        _definition("feature_product_automation_enabled", True, "message_actions", "商品自动化", "启用商品自动化动作", ("feature_items_enabled",), ("product-automation",), "high"),
        _definition("account_profile_auto_sync_enabled", True, "platform_background", "资料自动同步", "连接后自动同步账号资料", risk_level="medium"),
        _definition("scheduled_token_refresh_enabled", True, "platform_background", "周期 Token 刷新", "关闭后仅在连接需要时刷新", risk_level="high"),
        _definition("browser_cookie_refresh_enabled", True, "platform_background", "周期 Cookie 刷新", "关闭后保留手动恢复入口", risk_level="high"),
    )
)


FEATURE_FLAG_KEYS = FEATURE_FLAG_REGISTRY.keys()

