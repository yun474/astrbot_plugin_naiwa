"""根据整理好的奶蛙清单生成内置素材。

用法：
    python tools/build_assets.py 清单.json [--cache 原图缓存目录]

清单为列表，每项包含 id、name、description、analysis、group、source、source_url。
脚本会下载（或从缓存读取）原图，统一缩放为长边 1080 的 WebP，
并生成 resources/naiwa.json 与 resources/CREDITS.md。
"""

import argparse
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
LONG_SIDE = 1080
SOURCES = {
    "Nailong-Studio/NaiLoong-Universe": "奶蛙艺术圣殿",
    "GeorgeNaNN/nailong-memes": "nailong-memes",
}


def fetch(item: dict, cache: Path | None) -> bytes:
    if cache:
        hit = next(cache.glob(f"{item['id']}.*"), None)
        if hit:
            return hit.read_bytes()
    request = urllib.request.Request(item["source_url"], headers={"User-Agent": "naiwa-build"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{item['id']}{Path(item['source_url']).suffix.lower()}").write_bytes(data)
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()

    items = json.loads(args.manifest.read_text("utf-8"))
    images = RESOURCES / "images"
    images.mkdir(parents=True, exist_ok=True)
    for old in images.glob("*.webp"):
        old.unlink()

    catalog, credits = [], []
    for order, item in enumerate(items):
        if item["source"] not in SOURCES:
            raise SystemExit(f"{item['id']} 的来源未登记：{item['source']}")
        with Image.open(io.BytesIO(fetch(item, args.cache))) as source:
            art = source.convert("RGB")
        art.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
        art.save(images / f"{item['id']}.webp", "WEBP", quality=80, method=6)
        catalog.append(
            {
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "analysis": item["analysis"],
                "group": item["group"],
                "source": item["source"],
                "image": f"images/{item['id']}.webp",
                "enabled": True,
                "sort_order": order,
            }
        )
        credits.append(
            f"| {item['id']} | {item['name']} | {SOURCES[item['source']]} | [原图]({item['source_url']}) |"
        )

    (RESOURCES / "naiwa.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", "utf-8", newline="\n"
    )
    header = [
        "# 素材来源",
        "",
        "内置素材均来自以下仓库，经缩放后收录：",
        "",
        "- [Nailong-Studio/NaiLoong-Universe](https://github.com/Nailong-Studio/NaiLoong-Universe)"
        "（奶蛙艺术圣殿）：MIT。奶蛙为民间二创形象，角色原型权利归原权利人。",
        "- [GeorgeNaNN/nailong-memes](https://github.com/GeorgeNaNN/nailong-memes)"
        "：「来只奶龙」插件的默认图库，仓库标注 MIT，内容为网络收集的表情包。",
        "",
        "如果你是权利人并认为某件素材不宜收录，请提交 Issue，核实后会尽快下架。",
        "",
        "| 编号 | 名称 | 来源 | 原图 |",
        "| --- | --- | --- | --- |",
    ]
    (RESOURCES / "CREDITS.md").write_text(
        "\n".join(header + credits) + "\n", "utf-8", newline="\n"
    )
    size = sum(p.stat().st_size for p in images.glob("*.webp"))
    print(f"已生成 {len(catalog)} 件素材，共 {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
