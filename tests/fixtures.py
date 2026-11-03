"""测试用的官方名单与图包：在临时目录生成，不依赖网络和 GitHub Release。"""

import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from core.catalog.fingerprint import dhash


def picture(index: int, size=(64, 48), fmt="PNG") -> bytes:
    """每张图画上不同的色块，保证感知指纹互不相同。"""
    image = Image.new("RGB", size, (250, 240, 220))
    draw = ImageDraw.Draw(image)
    for step in range(4):
        x = (index * 13 + step * 17) % (size[0] - 12)
        y = (index * 7 + step * 11) % (size[1] - 12)
        draw.rectangle((x, y, x + 12, y + 12), fill=(30 + step * 50, 20 * index % 255, 90))
    with io.BytesIO() as output:
        image.save(output, fmt)
        return output.getvalue()


def make_official(resources: Path, count: int = 3, legacy: bool = True) -> dict:
    """写出官方名单、兜底图与历史指纹表，返回图包字节与各图片字节。"""
    resources.mkdir(parents=True, exist_ok=True)
    images, items = {}, []
    for index in range(count):
        item_id = f"item-{index}"
        data = picture(index)
        images[f"images/{item_id}.png"] = data
        items.append(
            {
                "id": item_id,
                "name": f"官方{index}",
                "description": "",
                "analysis": "官方签语",
                "group": "测试",
                "source": "",
                "image": f"images/{item_id}.png",
                "sha256": hashlib.sha256(data).hexdigest(),
                "enabled": True,
                "sort_order": index,
            }
        )
    with io.BytesIO() as buffer:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
            for name in sorted(images):
                archive.writestr(name, images[name])
        pack = buffer.getvalue()
    manifest = {
        "pack": {
            "tag": "assets-v1",
            "file": "naiwa-assets-v1.zip",
            "size": len(pack),
            "sha256": hashlib.sha256(pack).hexdigest(),
        },
        "items": items,
    }
    (resources / "naiwa.json").write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")
    (resources / "fallback").mkdir(exist_ok=True)
    (resources / "fallback" / "item-0.png").write_bytes(images["images/item-0.png"])
    table = {}
    if legacy:
        for item in items:
            with Image.open(io.BytesIO(images[item["image"]])) as image:
                table[item["id"]] = {
                    **{
                        k: [item[k]] for k in ("name", "description", "analysis", "group", "source")
                    },
                    "sort_order": [item["sort_order"]],
                    "dhash": [dhash(image)],
                }
    (resources / "legacy.json").write_text(json.dumps(table, ensure_ascii=False), "utf-8")
    return {"pack": pack, "images": images, "items": items}


def install(root: Path, fixture: dict):
    """模拟图包已经装好：按指纹把全部官方图放入 assets/。"""
    archive = root / "assets"
    archive.mkdir(parents=True, exist_ok=True)
    for item in fixture["items"]:
        data = fixture["images"][item["image"]]
        (archive / f"{item['sha256']}.png").write_bytes(data)
