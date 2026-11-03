import io
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import make_official, picture
from PIL import Image

from core.catalog import build_catalog, load_official, prepare
from core.config import NaiwaError


def reencode(data: bytes) -> bytes:
    """模拟旧版在安装时把内置图转成 JPEG。"""
    with Image.open(io.BytesIO(data)) as image, io.BytesIO() as output:
        image.convert("RGB").save(output, "JPEG", quality=88)
        return output.getvalue()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.resources, self.root = base / "resources", base / "data"
        self.fixture = make_official(self.resources, 3)
        self.official = load_official(self.resources).items
        self.catalog = self.root / "catalog"
        (self.catalog / "images").mkdir(parents=True)
        self.entries = []
        for item in self.fixture["items"]:
            name = f"images/{item['id']}.jpg"
            (self.catalog / name).write_bytes(reencode(self.fixture["images"][item["image"]]))
            fields = ("id", "name", "description", "analysis", "group", "source", "sort_order")
            self.entries.append({**{k: item[k] for k in fields}, "image": name, "enabled": True})

    def tearDown(self):
        self.temp.cleanup()

    def migrate(self):
        (self.catalog / "naiwa.json").write_text(
            json.dumps(self.entries, ensure_ascii=False), "utf-8"
        )
        return prepare(self.root, self.resources, self.official)

    def custom(self):
        return {e["id"]: e for e in json.loads((self.catalog / "custom.json").read_text("utf-8"))}

    def test_untouched_legacy_catalog_becomes_official_and_is_backed_up(self):
        summary = self.migrate()
        self.assertIn("官方原样 3 件", summary)
        self.assertEqual(self.custom(), {})
        self.assertFalse((self.catalog / "naiwa.json").exists())
        self.assertFalse(list((self.catalog / "images").iterdir()))
        (backup,) = self.catalog.glob("legacy-*")
        self.assertTrue((backup / "naiwa.json").is_file())
        self.assertEqual(len(list((backup / "images").iterdir())), 3)
        self.assertIsNone(prepare(self.root, self.resources, self.official))
        self.assertEqual(len(list(self.catalog.glob("legacy-*"))), 1)

    def test_admin_changes_become_overrides_and_deleted_items_stay_disabled(self):
        self.entries[0]["analysis"] = "改过的签语"
        (self.catalog / "images" / "item-0.jpg").write_bytes(picture(50, fmt="JPEG"))
        self.entries[1]["enabled"] = False
        del self.entries[2]
        (self.catalog / "images" / "mine.png").write_bytes(picture(60))
        mine = {
            "id": "mine",
            "name": "自己的",
            "description": "",
            "analysis": "自己的签语",
            "group": "自定义",
            "image": "images/mine.png",
        }
        self.entries.append(mine)
        summary = self.migrate()
        self.assertIn("覆盖 1 件，下架 2 件，自定义新增 1 件", summary)
        self.assertEqual(
            self.custom(),
            {
                "item-0": {"id": "item-0", "analysis": "改过的签语", "image": "images/item-0.jpg"},
                "item-1": {"id": "item-1", "enabled": False},
                "item-2": {"id": "item-2", "enabled": False},
                "mine": mine,
            },
        )
        # 只清理确认与官方一致的副本；没有条目引用的文件可能是管理员自己的，原样保留。
        images = {p.name for p in (self.catalog / "images").iterdir()}
        self.assertEqual(images, {"item-0.jpg", "item-2.jpg", "mine.png"})
        items = {i["id"]: i for i in build_catalog(self.root, self.official).items}
        self.assertEqual(items["item-0"]["analysis"], "改过的签语")
        self.assertEqual({k for k, v in items.items() if v["enabled"]}, {"item-0", "mine"})

    def test_old_backup_layout_with_digest_file_names_migrates(self):
        for index, entry in enumerate(self.entries):
            old = self.catalog / entry["image"]
            entry["image"] = f"images/{index:064x}.jpg"
            old.rename(self.catalog / entry["image"])
        self.migrate()
        self.assertEqual(self.custom(), {})

    def test_unreadable_legacy_catalog_is_left_untouched(self):
        (self.catalog / "naiwa.json").write_text("{broken", "utf-8")
        with self.assertRaises(NaiwaError):
            prepare(self.root, self.resources, self.official)
        self.assertEqual((self.catalog / "naiwa.json").read_text("utf-8"), "{broken")
        self.assertFalse((self.catalog / "custom.json").exists())
        with self.assertRaises(NaiwaError):
            build_catalog(self.root, self.official)


if __name__ == "__main__":
    unittest.main()
