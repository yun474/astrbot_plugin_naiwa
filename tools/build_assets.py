"""根据源清单生成官方图包与插件内置的官方名单。

用法：
    python tools/build_assets.py tools/naiwa-source.json --pack 版本号 [--cache 原图缓存目录]

源清单为列表，每项包含 id、name、description、analysis、group、source、source_url。
脚本会下载（或从缓存读取）原图，统一缩放为长边 1080 的 JPEG，并生成：
    dist/naiwa-assets-v{版本号}.zip   发布到 GitHub Release 的图包
    resources/naiwa.json             官方名单（含图包信息与每张图的指纹）
    resources/fallback/              随插件分发的兜底原版图
    resources/CREDITS.md             逐件来源表
"""

import argparse
import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
DIST = ROOT / "dist"
REPO = "yun474/astrbot_plugin_naiwa"
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


def encode(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        art = source.convert("RGB")
    art.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
    with io.BytesIO() as output:
        art.save(output, "JPEG", quality=88, optimize=True)
        return output.getvalue()


def write_credits(items: list[dict]):
    header = [
        "# 素材来源",
        "",
        "官方图包中的素材均来自以下仓库，经缩放后收录：",
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
    rows = [
        f"| {x['id']} | {x['name']} | {SOURCES[x['source']]} | [原图]({x['source_url']}) |"
        for x in items
    ]
    (RESOURCES / "CREDITS.md").write_text("\n".join(header + rows) + "\n", "utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pack", type=int, required=True, help="图包版本号，每次发新图包加一")
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()

    items = json.loads(args.manifest.read_text("utf-8"))
    tag, file = f"assets-v{args.pack}", f"naiwa-assets-v{args.pack}.zip"
    DIST.mkdir(exist_ok=True)
    pack = DIST / file
    catalog, images = [], {}
    for order, item in enumerate(items):
        if item["source"] not in SOURCES:
            raise SystemExit(f"{item['id']} 的来源未登记：{item['source']}")
        data = encode(fetch(item, args.cache))
        images[f"images/{item['id']}.jpg"] = data
        catalog.append(
            {
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "analysis": item["analysis"],
                "group": item["group"],
                "source": item["source"],
                "image": f"images/{item['id']}.jpg",
                "sha256": hashlib.sha256(data).hexdigest(),
                "enabled": True,
                "sort_order": order,
            }
        )

    # 固定文件顺序与时间戳，同样的输入总是得到同样的图包指纹。
    with zipfile.ZipFile(pack, "w", zipfile.ZIP_STORED) as archive:
        for name in sorted(images):
            archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), images[name])
    raw = pack.read_bytes()
    manifest = {
        "pack": {
            "tag": tag,
            "file": file,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "items": catalog,
    }
    (RESOURCES / "naiwa.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8", newline="\n"
    )

    # 兜底图与图包内同一张图字节一致，首次安装时可直接使用。
    fallback = RESOURCES / "fallback"
    shutil.rmtree(fallback, ignore_errors=True)
    fallback.mkdir()
    first = catalog[0]["image"]
    (fallback / Path(first).name).write_bytes(images[first])
    shutil.rmtree(RESOURCES / "images", ignore_errors=True)
    write_credits(items)

    print(f"已生成 {len(catalog)} 件素材，图包 {pack.relative_to(ROOT)} 共 {len(raw) / 1e6:.1f} MB")
    print("确认无误后先发布图包，再推送插件代码：")
    print(
        f'gh release create {tag} "{pack}" --repo {REPO} '
        f'--title "图包 v{args.pack}" --notes "官方图包，供插件自动下载，请勿删除。"'
    )


if __name__ == "__main__":
    main()
