import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import install, make_official, picture

from core.catalog import build_catalog, load_official, prepare
from core.config import NaiwaError


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.resources, self.root = base / "resources", base / "data"
        self.fixture = make_official(self.resources, 3)
        self.official = load_official(self.resources).items
        prepare(self.root, self.resources, self.official)
        install(self.root, self.fixture)
        self.catalog = self.root / "catalog"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, entries):
        (self.catalog / "custom.json").write_text(json.dumps(entries, ensure_ascii=False), "utf-8")

    def build(self, current=None):
        result = build_catalog(self.root, self.official, current)
        return result, {item["id"]: item for item in result.items}

    def test_overrides_only_replace_given_fields_and_can_disable(self):
        self.write([{"id": "item-0", "name": "改名"}, {"id": "item-1", "enabled": False}])
        result, items = self.build()
        self.assertEqual(items["item-0"]["name"], "改名")
        self.assertEqual(items["item-0"]["analysis"], "官方签语")
        self.assertFalse(items["item-1"]["enabled"])
        self.assertEqual(result.pending, [])

    def test_custom_image_and_new_entries_follow_official_order(self):
        data = picture(42)
        (self.catalog / "images" / "mine.png").write_bytes(data)
        new = {
            "id": "my-new",
            "name": "新",
            "description": "",
            "analysis": "签语",
            "group": "自定义",
        }
        self.write(
            [{"id": "item-2", "image": "images/mine.png"}, {**new, "image": "images/mine.png"}]
        )
        _, items = self.build()
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(items["item-2"]["asset"], f"{digest}.png")
        self.assertEqual(items["my-new"]["sort_order"], 3)
        self.assertTrue(items["my-new"]["enabled"])

    def test_partial_entry_for_removed_official_item_is_ignored_with_warning(self):
        self.write([{"id": "gone", "enabled": False}])
        result, items = self.build()
        self.assertEqual(set(items), {"item-0", "item-1", "item-2"})
        self.assertIn("gone", result.warnings[0])

    def test_missing_official_image_keeps_current_asset_and_new_item_waits(self):
        archive = self.root / "assets"
        for item in self.fixture["items"][1:]:
            (archive / f"{item['sha256']}.png").unlink()
        (archive / "old.png").write_bytes(picture(7))
        result, items = self.build({"item-1": "old.png"})
        self.assertEqual(items["item-1"]["asset"], "old.png")
        self.assertNotIn("item-2", items)
        self.assertEqual(result.pending, ["item-2"])

    def test_invalid_custom_file_is_rejected(self):
        (self.catalog / "custom.json").write_text("{", "utf-8")
        with self.assertRaises(NaiwaError):
            self.build()

    def test_prepare_keeps_custom_file_and_exports_readonly_official_list(self):
        self.write([{"id": "item-0", "enabled": False}])
        self.assertIsNone(prepare(self.root, self.resources, self.official))
        custom = json.loads((self.catalog / "custom.json").read_text("utf-8"))
        self.assertEqual(custom, [{"id": "item-0", "enabled": False}])
        readonly = json.loads((self.catalog / "official.readonly.json").read_text("utf-8"))
        self.assertEqual([item["id"] for item in readonly["items"]], ["item-0", "item-1", "item-2"])


if __name__ == "__main__":
    unittest.main()
