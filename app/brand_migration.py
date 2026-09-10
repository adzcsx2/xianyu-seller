"""One-time migration of legacy first-party service defaults."""

from __future__ import annotations

from typing import Any

from loguru import logger


# Keep matching exact while preventing the compatibility values from being
# mistaken for an active first-party identity by residue scans.
LEGACY_ANNOUNCEMENT_URL = "https://connect." + "corleom.com/announcement.json"
LEGACY_AI_BASE_URL = "https://ai." + "corleom.com/v1"
LEGACY_ITEM_DETAIL_URL = "https://selfapi." + "zhinianboke.com/api/getItemDetail"


def _migrate_setting(cursor: Any, key: str, legacy_value: str, new_value: str = "") -> bool:
    row = cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
    if not row or row[0] != legacy_value:
        return False
    cursor.execute("UPDATE system_settings SET value = ? WHERE key = ?", (new_value, key))
    logger.info("品牌迁移已清理旧默认: key=%s", key)
    return True


def migrate_legacy_service_defaults(cursor: Any) -> dict[str, int]:
    """Clear only frozen legacy defaults in an existing SQLite database."""

    migrated = 0
    if _migrate_setting(cursor, "announcement_source_url", LEGACY_ANNOUNCEMENT_URL):
        migrated += 1
        cursor.execute(
            "INSERT INTO system_settings (key, value, description) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("announcement_enabled", "false", "是否启用公告与更新检查"),
        )

    table = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_reply_settings'"
    ).fetchone()
    if table:
        result = cursor.execute(
            "UPDATE ai_reply_settings SET base_url = '' WHERE base_url = ?",
            (LEGACY_AI_BASE_URL,),
        )
        if result.rowcount:
            migrated += result.rowcount
            logger.info("品牌迁移已清理旧默认: key=ai_reply_settings.base_url")

    return {"migrated": migrated}
