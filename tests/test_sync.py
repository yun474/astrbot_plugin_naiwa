import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from fixtures import install, make_official

from core.assets import AssetError, AssetSync, sources
from core.catalog import load_official, prepare


def without_proxy():
    env = patch.dict(os.environ)
    env.start()
    for key in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY"):
        os.environ.pop(key, None)
    return env


class SyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.resources, self.root = base / "resources", base / "data"
        self.fixture = make_official(self.resources, 3)
        self.official = load_official(self.resources)
        prepare(self.root, self.resources, self.official.items)
        self.env = without_proxy()

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def assets(self):
        return sorted(p.name for p in (self.root / "assets").iterdir())

    async def serve(self, handlers: dict):
        app = web.Application()
        for prefix, handler in handlers.items():
            app.router.add_get(f"/{prefix}/{{tail:.*}}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        return f"http://127.0.0.1:{runner.addresses[0][1]}"

    async def test_local_pack_installs_without_network(self):
        (self.root / "packs" / "随便起的名字.zip").write_bytes(self.fixture["pack"])
        sync = AssetSync(self.root, self.official)
        with patch("core.assets.sync.aiohttp.ClientSession", side_effect=AssertionError):
            self.assertEqual(await sync.run(), (2, "本地图包"))
        self.assertTrue(sync.installed_once)
        self.assertEqual(sync.missing(), [])
        self.assertTrue(AssetSync(self.root, self.official).installed_once)

    async def test_nothing_missing_makes_no_request(self):
        install(self.root, self.fixture)
        with patch("core.assets.sync.aiohttp.ClientSession", side_effect=AssertionError):
            self.assertEqual(await AssetSync(self.root, self.official).run(), (0, ""))

    def test_unexpected_or_tampered_pack_contents_are_rejected(self):
        sync = AssetSync(self.root, self.official)
        before = self.assets()
        images = self.fixture["images"]
        for files in (
            {**images, "../evil.png": b"x"},
            {**images, "images/extra.png": b"x"},
            {**images, "images/item-1.png": images["images/item-2.png"]},
        ):
            with self.subTest(files=sorted(files)), io.BytesIO() as buffer:
                with zipfile.ZipFile(buffer, "w") as archive:
                    for name, data in files.items():
                        archive.writestr(name, data)
                with self.assertRaises(AssetError):
                    sync._install(buffer.getvalue(), sync.missing())
                self.assertEqual(self.assets(), before)

    async def test_failed_mirror_falls_back_to_next_one(self):
        hits = []

        async def broken(request):
            return web.Response(status=502)

        async def good(request):
            hits.append(request.match_info["tail"])
            return web.Response(body=self.fixture["pack"])

        base = await self.serve({"bad": broken, "good": good})
        sync = AssetSync(self.root, self.official, (f"{base}/bad/", f"{base}/good/"))
        with patch.object(sources, "BUILTIN_MIRRORS", ()):
            count, _ = await sync.run()
        self.assertEqual(count, 2)
        self.assertIn(
            "https://github.com/yun474/astrbot_plugin_naiwa/releases/download/"
            "assets-v1/naiwa-assets-v1.zip",
            hits,
        )
        self.assertEqual(sync.missing(), [])

    async def test_failure_is_recorded_with_backoff_and_notice(self):
        async def broken(request):
            return web.Response(status=404)

        base = await self.serve({"bad": broken})
        sync = AssetSync(self.root, self.official, (f"{base}/bad/",))
        with patch.object(sources, "BUILTIN_MIRRORS", ()):
            with self.assertRaises(AssetError) as caught:
                await sync.run()
        self.assertIn("HTTP 404", str(caught.exception))
        reloaded = AssetSync(self.root, self.official)
        self.assertEqual((reloaded.failures, reloaded.retry_delay()), (1, 60))
        self.assertFalse(reloaded.installed_once)
        self.assertIn("下载失败", reloaded.status(2))
        self.assertEqual(reloaded.notice(), "奶蛙图库正在首次下载，请稍后再试。")

    def test_proxy_moves_direct_github_ahead_of_public_mirrors(self):
        extra = ("https://mine.example/",)
        plain = [name for name, _ in sources.candidates("u", extra)]
        self.assertEqual((plain[0], plain[-1]), ("mine.example", "GitHub 直连"))
        with patch.dict(os.environ, {"https_proxy": "http://proxy.example:7890"}):
            proxied = [name for name, _ in sources.candidates("u", extra)]
        self.assertEqual(proxied[:2], ["mine.example", "GitHub 直连"])


if __name__ == "__main__":
    unittest.main()
