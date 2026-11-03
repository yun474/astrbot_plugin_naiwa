import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.catalog import read_catalog
from core.config import NaiwaError, Settings
from core.rendering import render_today
from core.views import image_size, today_message


class NaiwaCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "catalog" / "images").mkdir(parents=True)
        Image.new("RGB", (160, 90), (200, 150, 40)).save(
            self.root / "catalog" / "images" / "wide.jpg", "JPEG"
        )

    def tearDown(self):
        self.temp.cleanup()

    def write(self, **overrides):
        item = {
            "id": "wide",
            "name": "横图",
            "description": "",
            "analysis": "你笑了。",
            "group": "伍·咏颂",
            "source": "Nailong-Studio/NaiLoong-Universe",
            "image": "images/wide.jpg",
        }
        item.update(overrides)
        (self.root / "catalog" / "naiwa.json").write_text(json.dumps([item]), "utf-8")

    def test_empty_description_is_allowed_and_image_size_comes_from_file(self):
        self.write()
        (item,) = read_catalog(self.root)
        self.assertEqual(item["description"], "")
        self.assertEqual(item["group_name"], "伍·咏颂")
        self.assertEqual((item["width"], item["height"]), (160, 90))

    def test_group_is_required(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                self.write(group=value)
                with self.assertRaises(NaiwaError):
                    read_catalog(self.root)


class NaiwaMessageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        Image.new("RGB", (300, 400), (90, 120, 200)).save(self.root / "assets" / "tall.jpg", "JPEG")
        self.item = {
            "id": "nw-5-001",
            "name": "捧腹大笑",
            "description": "",
            "analysis": "你笑了。",
            "asset": "tall.jpg",
            "group_name": "伍·咏颂",
            "source": "Nailong-Studio/NaiLoong-Universe",
            "width": 300,
            "height": 400,
            "enabled": 1,
        }
        self.progress = {"unlocked": 1, "total": 3, "active_total": 120}

    def tearDown(self):
        self.temp.cleanup()

    def result(self, **item):
        return {
            "item": {**self.item, **item},
            "day": "2026-11-03",
            "created": True,
            "count": 3,
            "new_species": False,
            "repeat_streak": 0,
        }

    def test_markdown_keeps_ratio_and_skips_empty_description(self):
        self.assertEqual(image_size(self.item), (480, 640))
        self.assertEqual(image_size({"width": 0, "height": 0}), (640, 640))
        user = {"id": 1, "open_id": "member"}
        text = today_message(Settings(), self.root, user, self.result(), self.progress).text
        self.assertIn("### 今日奶娃 · 第 3 次相遇", text)
        self.assertIn("**捧腹大笑** · 伍·咏颂", text)
        self.assertIn("![奶娃 #480px #640px]", text)
        self.assertIn("\n\n> 你笑了。\n\n", text)
        self.assertNotIn(">\n>", text)

    def test_today_card_is_shorter_without_description(self):
        plain = render_today(self.root, self.result(), self.progress, "第 3 次相遇", "", False)
        titled = render_today(
            self.root, self.result(description="小标题"), self.progress, "新收集！", "", True
        )
        self.assertEqual(plain.width, 1080)
        self.assertLess(plain.height, titled.height)
        with Image.open(io.BytesIO(plain.data)) as image:
            self.assertEqual(image.format, "PNG")
