import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import app.db_manager as db_module
from app.db_manager import DBManager
from app.reply_server import update_card as update_card_route


class CardInventoryConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = DBManager(os.path.join(self.temp_dir.name, "cards.db"))
        cursor = self.manager.conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (id, username, email, password_hash)
            VALUES (1, 'owner', 'owner@example.com', 'x')
            """
        )
        cursor.execute(
            """
            INSERT INTO cards (name, type, data_content, enabled, user_id)
            VALUES ('batch', 'data', 'CODE-A\nCODE-B\nCODE-C', 1, 1)
            """
        )
        self.card_id = cursor.lastrowid
        self.manager.conn.commit()

    def tearDown(self):
        self.manager.close()
        self.temp_dir.cleanup()

    def _card(self):
        return self.manager.get_card_by_id(self.card_id, user_id=1)

    def test_card_read_exposes_inventory_revision_without_revealing_content(self):
        card = self._card()
        listed_card = next(
            item for item in self.manager.get_all_cards(user_id=1)
            if item["id"] == self.card_id
        )

        self.assertRegex(card["inventory_revision"], r"^[0-9a-f]{64}$")
        self.assertEqual(card["inventory_revision"], listed_card["inventory_revision"])

    def test_stale_editor_cannot_restore_consumed_inventory(self):
        stale_card = self._card()
        self.assertEqual("CODE-A", self.manager.consume_batch_data(self.card_id))

        with self.assertRaisesRegex(RuntimeError, "库存已变化"):
            self.manager.update_card(
                card_id=self.card_id,
                data_content=stale_card["data_content"],
                expected_inventory_revision=stale_card["inventory_revision"],
                user_id=1,
            )

        self.assertEqual("CODE-B\nCODE-C", self._card()["data_content"])

    def test_current_revision_allows_intentional_inventory_edit(self):
        card = self._card()

        updated = self.manager.update_card(
            card_id=self.card_id,
            data_content="CODE-A\nCODE-B\nCODE-C\nCODE-D",
            expected_inventory_revision=card["inventory_revision"],
            user_id=1,
        )

        self.assertTrue(updated)
        self.assertEqual(4, len(self._card()["data_content"].splitlines()))

    def test_inventory_replacement_requires_revision(self):
        with self.assertRaisesRegex(RuntimeError, "库存版本"):
            self.manager.update_card(
                card_id=self.card_id,
                data_content="CODE-A\nCODE-B",
                user_id=1,
            )

        self.assertEqual(3, len(self._card()["data_content"].splitlines()))

    def test_metadata_only_update_does_not_require_inventory_revision(self):
        updated = self.manager.update_card(
            card_id=self.card_id,
            name="renamed",
            user_id=1,
        )

        self.assertTrue(updated)
        self.assertEqual("renamed", self._card()["name"])

    def test_api_maps_inventory_conflict_to_http_409(self):
        conflict_type = getattr(db_module, "CardInventoryConflict", RuntimeError)
        with patch(
            "app.db_manager.db_manager.update_card",
            side_effect=conflict_type("卡密库存已变化，请刷新后重试"),
        ):
            with self.assertRaises(HTTPException) as context:
                update_card_route(
                    self.card_id,
                    {
                        "type": "data",
                        "data_content": "CODE-A\nCODE-B\nCODE-C",
                        "expected_inventory_revision": "stale",
                    },
                    current_user={"user_id": 1, "username": "owner"},
                )

        self.assertEqual(409, context.exception.status_code)


if __name__ == "__main__":
    unittest.main()
