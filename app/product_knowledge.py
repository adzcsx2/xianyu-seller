"""轻量商品知识库：公开 seed、确定性检索和回复安全策略。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.db_manager import KnowledgeVersionConflict
from app.knowledge_runtime import KnowledgeRuntimeService


SAFETY_REPLY = "目前没有收到玩家反馈有封号情况出现。"
COMMERCIAL_SENSITIVE_REPLY = "这个问题涉及内部信息，暂不提供。"
HUMAN_CONFIRMATION_REPLY = "这个问题需要人工确认后回复。"

ALLOWED_CATEGORIES = {
    "product",
    "pricing",
    "region",
    "install",
    "activation",
    "feature",
    "limitation",
    "support",
}

MAX_KNOWLEDGE_ENTRIES = 200
MAX_KNOWLEDGE_PAYLOAD_BYTES = 512 * 1024
MAX_KNOWLEDGE_KEY_LENGTH = 80
MAX_ANSWER_LENGTH = 800
MAX_QUESTION_PATTERNS = 20
MAX_QUESTION_PATTERN_LENGTH = 80
MAX_KEYWORDS = 30
MAX_KEYWORD_LENGTH = 32
MAX_SOURCE_REFS = 8
MAX_SOURCE_REF_LENGTH = 240

_SAFETY_TERMS = (
    "封号",
    "封禁",
    "会封",
    "被封",
    "安全",
    "安全吗",
    "安全不",
    "账号安全",
    "检测",
    "反作弊",
    "绕检测",
    "规避检测",
    "风控",
    "ban",
    "banned",
    "account risk",
)

_COMMERCIAL_TERMS = (
    "源码",
    "源代码",
    "技术原理",
    "怎么实现",
    "反编译",
    "偏移",
    "offset",
    "内存地址",
    "特征码",
    "aob",
    "管理后台密码",
    "数据库内容",
    "数据库地址",
    "服务器配置",
    "api key",
    "apikey",
    "密钥",
    "cookie",
    "token",
    "成本",
    "利润",
    "进价",
    "供应商",
    "供应渠道",
    "销售数据",
    "完整卡密",
    "全部激活码",
    "库存明文",
    "其他买家",
    "订单资料",
    "账号资料",
)

_OUTPUT_SECRET_TERMS = (
    "api key",
    "apikey",
    "密钥",
    "cookie",
    "token",
    "password",
    "密码",
    "完整激活码",
    "库存明文",
)


class ProductKnowledgeService:
    """在现有 DBManager 上提供按账号/商品隔离的知识能力。"""

    SEED_PATH = Path(__file__).resolve().parent / "knowledge" / "passistant_public_v1.json"

    def __init__(self, db_manager):
        self.db_manager = db_manager

    @staticmethod
    def normalize_text(value: Any) -> str:
        text = "" if value is None else str(value)
        text = unicodedata.normalize("NFKC", text).lower()
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def classify_policy_intent(cls, message: str) -> str:
        """返回 safety、commercial_sensitive 或 public；safety 优先级最高。"""
        text = cls.normalize_text(message)
        if any(term in text for term in _SAFETY_TERMS):
            return "safety"
        if any(term in text for term in _COMMERCIAL_TERMS):
            return "commercial_sensitive"
        return "public"

    @staticmethod
    def fixed_reply(policy_intent: str) -> Optional[str]:
        return {
            "safety": SAFETY_REPLY,
            "commercial_sensitive": COMMERCIAL_SENSITIVE_REPLY,
        }.get(policy_intent)

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def seed_checksum(cls, seed: Dict[str, Any]) -> str:
        """计算与条目排列无关的 seed SHA-256。"""
        normalized = dict(seed)
        normalized["entries"] = sorted(
            list(seed.get("entries", [])),
            key=lambda entry: str(entry.get("knowledge_key", "")),
        )
        return hashlib.sha256(cls._canonical_json(normalized)).hexdigest()

    @classmethod
    def load_seed(cls, path: Optional[Path] = None) -> Dict[str, Any]:
        seed_path = Path(path) if path else cls.SEED_PATH
        with seed_path.open("r", encoding="utf-8") as handle:
            seed = json.load(handle)
        cls.validate_seed(seed)
        return seed

    @staticmethod
    def _validate_string_list(
        value: Any,
        field: str,
        maximum: int,
        item_maximum: int,
    ) -> List[str]:
        if not isinstance(value, list) or len(value) > maximum:
            raise ValueError(f"{field} must be a list with at most {maximum} values")
        normalized: List[str] = []
        seen = set()
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{field} must contain non-empty strings")
            item = item.strip()
            if len(item) > item_maximum:
                raise ValueError(f"{field} values cannot exceed {item_maximum} characters")
            if item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized

    @classmethod
    def validate_entries(cls, entries: Iterable[Dict[str, Any]], *, require_sources: bool = False) -> List[Dict[str, Any]]:
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
        if len(entries) > MAX_KNOWLEDGE_ENTRIES:
            raise ValueError(f"entries cannot exceed {MAX_KNOWLEDGE_ENTRIES}")
        try:
            payload_size = len(cls._canonical_json(entries))
        except (TypeError, ValueError) as exc:
            raise ValueError("entries must contain JSON-compatible values") from exc
        if payload_size > MAX_KNOWLEDGE_PAYLOAD_BYTES:
            raise ValueError("knowledge payload cannot exceed 512 KiB")

        normalized_entries: List[Dict[str, Any]] = []
        keys = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each entry must be an object")
            key = entry.get("knowledge_key")
            category = entry.get("category")
            answer = entry.get("answer")
            if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", key):
                raise ValueError("knowledge_key is invalid")
            if key in keys:
                raise ValueError(f"duplicate knowledge_key: {key}")
            keys.add(key)
            if category not in ALLOWED_CATEGORIES:
                raise ValueError(f"unsupported category: {category}")
            if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= MAX_ANSWER_LENGTH:
                raise ValueError(f"answer must contain 1-{MAX_ANSWER_LENGTH} characters")
            patterns = cls._validate_string_list(
                entry.get("question_patterns", []),
                "question_patterns",
                MAX_QUESTION_PATTERNS,
                MAX_QUESTION_PATTERN_LENGTH,
            )
            keywords = cls._validate_string_list(
                entry.get("keywords", []),
                "keywords",
                MAX_KEYWORDS,
                MAX_KEYWORD_LENGTH,
            )
            sources = cls._validate_string_list(
                entry.get("source_refs", []),
                "source_refs",
                MAX_SOURCE_REFS,
                MAX_SOURCE_REF_LENGTH,
            )
            if require_sources and not sources:
                raise ValueError(f"source_refs required: {key}")
            priority = entry.get("priority", 0)
            if isinstance(priority, bool) or not isinstance(priority, int):
                raise ValueError("priority must be an integer")
            if not -100 <= priority <= 100:
                raise ValueError("priority must be between -100 and 100")
            enabled = entry.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")

            public_text = cls.normalize_text("\n".join([key, category, *patterns, *keywords, answer]))
            blocked = [term for term in (*_SAFETY_TERMS, *_COMMERCIAL_TERMS) if term in public_text]
            if blocked:
                raise ValueError(f"entry contains blocked policy term: {blocked[0]}")
            normalized_entries.append({
                "knowledge_key": key,
                "category": category,
                "question_patterns": patterns,
                "keywords": keywords,
                "answer": answer.strip(),
                "source_refs": sources,
                "priority": priority,
                "enabled": enabled,
            })
        return normalized_entries

    @classmethod
    def validate_seed(cls, seed: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(seed, dict):
            raise ValueError("seed must be an object")
        if seed.get("schema_version") != 1:
            raise ValueError("unsupported seed schema")
        if seed.get("product_key") != "passistant":
            raise ValueError("seed product_key must be passistant")
        if seed.get("display_name") != "Passistant 知识库":
            raise ValueError("seed display_name is invalid")
        if not isinstance(seed.get("seed_version"), str) or not seed["seed_version"].strip():
            raise ValueError("seed_version is required")
        entries = cls.validate_entries(seed.get("entries"), require_sources=True)
        seed["entries"] = entries
        return seed

    def retrieve(
        self,
        cookie_id: str,
        item_id: str,
        message: str,
        *,
        limit: int = 5,
        max_characters: int = 2500,
    ) -> List[Dict[str, Any]]:
        del max_characters  # 字符预算在 build_context 中统一执行。
        if not self.normalize_text(message):
            return []
        result = KnowledgeRuntimeService(self.db_manager).match(
            cookie_id, item_id, message, limit=limit
        )
        return [
            {
                **match,
                "knowledge_key": match.get("qa_key") or match.get("fact_key") or "",
                "answer": match.get("answer") or match.get("content") or "",
            }
            for match in result.get("matches", [])
        ]

    def protect_current_price(self, cookie_id: str, item_id: str) -> bool:
        """只有当前商品绑定库中的结构化价格规则才启用价格保护。"""
        snapshot = KnowledgeRuntimeService(self.db_manager).snapshot(cookie_id, item_id)
        return any(
            rule.get("rule_type") in {"pricing_policy", "bargain_policy"}
            for rule in snapshot.get("rules", [])
        )

    @staticmethod
    def build_context(matches: List[Dict[str, Any]], max_characters: int = 2500) -> str:
        return KnowledgeRuntimeService.build_context(matches, max_characters=max_characters)

    @classmethod
    def _contains_output_sensitive_text(cls, reply: str) -> bool:
        text = cls.normalize_text(reply)
        return any(term in text for term in _OUTPUT_SECRET_TERMS)

    @classmethod
    def validate_model_reply(
        cls,
        reply: Optional[str],
        original_message: str,
        matches: List[Dict[str, Any]],
    ) -> Optional[str]:
        """仅执行所有商品都必须遵守的秘密、路径和系统提示词防护。"""
        if not isinstance(reply, str) or not reply.strip():
            return None
        if cls._contains_output_sensitive_text(reply):
            return matches[0]["answer"] if matches else HUMAN_CONFIRMATION_REPLY
        if re.search(r"(?:[A-Za-z]:\\|/app/|source_refs|knowledge_key|system prompt)", reply, re.IGNORECASE):
            return matches[0]["answer"] if matches else HUMAN_CONFIRMATION_REPLY
        return reply.strip()


__all__ = [
    "COMMERCIAL_SENSITIVE_REPLY",
    "HUMAN_CONFIRMATION_REPLY",
    "KnowledgeVersionConflict",
    "ProductKnowledgeService",
    "SAFETY_REPLY",
]
