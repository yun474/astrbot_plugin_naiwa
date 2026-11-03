"""补齐官方图：优先使用管理员放入的本地图包，否则从 Release 下载，校验后按指纹存入 assets/。"""

import asyncio
import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import aiohttp

from ..catalog import Official
from ..catalog.images import MAX_BYTES, store
from .sources import candidates, rank, release_url

RETRY_DELAYS = (60, 300, 900, 3600)


class AssetError(Exception):
    pass


class AssetSync:
    def __init__(self, root: Path, official: Official, extra_mirrors: tuple[str, ...] = ()):
        self.root = root
        self.official = official
        self.extra_mirrors = extra_mirrors
        self.state_path = root / "catalog" / "sync.json"
        try:
            self.state = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            self.state = {}

    @property
    def installed_once(self) -> bool:
        return bool(self.state.get("installed_once"))

    @property
    def failures(self) -> int:
        return int(self.state.get("failures", 0))

    def retry_delay(self) -> int:
        return RETRY_DELAYS[min(max(self.failures, 1), len(RETRY_DELAYS)) - 1]

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.state, ensure_ascii=False), "utf-8")
        temp.replace(self.state_path)

    def mark_installed(self):
        self.state["installed_once"] = True
        self._save()

    def missing(self) -> list[dict]:
        archive = self.root / "assets"
        return [item for item in self.official.items if not (archive / item["asset"]).is_file()]

    def notice(self) -> str:
        if self.failures >= 3:
            return "奶蛙图库下载失败，请联系管理员查看插件日志。"
        return "奶蛙图库正在首次下载，请稍后再试。"

    def status(self, pending: int) -> str:
        total = sum(item["enabled"] for item in self.official.items)
        ready = f"官方图库 {max(total - pending, 0)}/{total}"
        if not pending:
            return f"{ready} 已就绪。"
        if self.failures:
            return f"{ready}，下载失败：{self.state.get('last_error', '')[:160]}，稍后自动重试。"
        return f"{ready}，正在后台下载。"

    async def run(self) -> tuple[int, str]:
        """补齐缺失的官方图，返回新装入的张数与来源；失败时抛出 AssetError。"""
        missing = await asyncio.to_thread(self.missing)
        if not missing:
            return 0, ""
        try:
            raw = await asyncio.to_thread(self._local_pack)
            source = "本地图包"
            if raw is None:
                raw, source = await self._download()
            count = await asyncio.to_thread(self._install, raw, missing)
        except AssetError as exc:
            self.state.update(
                failures=self.failures + 1, last_error=str(exc), last_attempt=time.time()
            )
            await asyncio.to_thread(self._save)
            raise
        self.state.update(
            installed_once=True, failures=0, last_error="", source=source, last_success=time.time()
        )
        await asyncio.to_thread(self._save)
        return count, source

    def _matches(self, raw: bytes) -> bool:
        pack = self.official.pack
        return len(raw) == pack.size and hashlib.sha256(raw).hexdigest() == pack.sha256

    def _local_pack(self) -> bytes | None:
        # 按指纹识别，管理员手动下载的图包改了文件名也能用。
        for path in sorted((self.root / "packs").glob("*.zip")):
            try:
                if path.stat().st_size == self.official.pack.size:
                    raw = path.read_bytes()
                    if self._matches(raw):
                        return raw
            except OSError:
                continue
        return None

    async def _download(self) -> tuple[bytes, str]:
        pack = self.official.pack
        url = release_url(pack.tag, pack.file)
        timeout = aiohttp.ClientTimeout(total=600, sock_connect=10, sock_read=30)
        errors = []
        # trust_env 让 AstrBot 后台配置的代理对图包下载同样生效。
        async with aiohttp.ClientSession(trust_env=True, timeout=timeout) as session:
            for name, link in await rank(session, candidates(url, self.extra_mirrors)):
                try:
                    async with session.get(link) as response:
                        if response.status != 200:
                            raise AssetError(f"HTTP {response.status}")
                        data = bytearray()
                        async for chunk in response.content.iter_chunked(65536):
                            data += chunk
                            if len(data) > pack.size:
                                raise AssetError("文件大小不符")
                    raw = bytes(data)
                    if not self._matches(raw):
                        raise AssetError("图包校验失败")
                    return raw, name
                except AssetError as exc:
                    errors.append(f"{name}：{exc}")
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    errors.append(f"{name}：{type(exc).__name__}")
        raise AssetError("所有线路均下载失败（" + "；".join(errors) + "）")

    def _install(self, raw: bytes, missing: list[dict]) -> int:
        expected = {item["image"] for item in self.official.items}
        archive = self.root / "assets"
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as pack:
                names = pack.namelist()
                if len(set(names)) != len(names) or not set(names) <= expected:
                    raise AssetError("图包内容与官方名单不符。")
                for item in missing:
                    try:
                        info = pack.getinfo(item["image"])
                    except KeyError:
                        raise AssetError(f"图包缺少 {item['id']} 的图片。") from None
                    if info.file_size > MAX_BYTES:
                        raise AssetError(f"图包中 {item['id']} 的图片过大。")
                    data = pack.read(info)
                    if hashlib.sha256(data).hexdigest() != item["sha256"]:
                        raise AssetError(f"图包中 {item['id']} 的图片指纹不符。")
                    store(archive / item["asset"], data)
        except (zipfile.BadZipFile, OSError) as exc:
            raise AssetError(f"图包无法解压：{type(exc).__name__}") from exc
        return len(missing)
