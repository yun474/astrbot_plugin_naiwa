"""图包下载线路：GitHub Release 原始地址加上国内可用的加速前缀。"""

import asyncio
import os
import time
from urllib.parse import urlsplit

import aiohttp

REPO = "yun474/astrbot_plugin_naiwa"
# 「前缀 + GitHub 原始下载地址」形式的公共加速线路，按 2026-11 国内多节点实测可用率排序。
# 公共线路随时可能失效，发新版时按需更新；空字符串表示 GitHub 直连。
BUILTIN_MIRRORS = (
    "https://gh-proxy.com/",
    "https://hk.gh-proxy.com/",
    "https://ghproxy.net/",
    "https://edgeone.gh-proxy.com/",
    "https://ghfast.top/",
    "https://gh.dpik.top/",
    "",
)
PROBE_TIMEOUT = 8


def release_url(tag: str, file: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}/{file}"


def label(prefix: str) -> str:
    return urlsplit(prefix).netloc or "GitHub 直连"


def candidates(url: str, extra: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    builtin = list(BUILTIN_MIRRORS)
    # AstrBot 配置了代理时会写入环境变量，此时直连 GitHub 通常最稳。
    if "" in builtin and (os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")):
        builtin.remove("")
        builtin.insert(0, "")
    result, seen = [], set()
    for prefix in (*extra, *builtin):
        if prefix not in seen:
            seen.add(prefix)
            result.append((label(prefix), prefix + url))
    return result


async def rank(session: aiohttp.ClientSession, sources: list[tuple[str, str]]) -> list:
    """并发探测各线路，响应快的排前面；探测失败的保持原顺序排在最后。"""

    async def probe(url: str) -> float | None:
        start = time.monotonic()
        try:
            async with session.get(
                url,
                headers={"Range": "bytes=0-1023"},
                timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT),
            ) as response:
                if response.status not in (200, 206):
                    return None
                await response.content.read(1024)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return None
        return time.monotonic() - start

    elapsed = await asyncio.gather(*(probe(url) for _, url in sources))
    order = sorted(
        range(len(sources)),
        key=lambda i: (elapsed[i] is None, elapsed[i] or 0, i),
    )
    return [sources[i] for i in order]
