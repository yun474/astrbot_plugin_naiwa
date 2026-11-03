import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image

from .config import NaiwaError


def initialize_catalog(data_dir: Path, resources: Path) -> None:
    target = data_dir / "catalog"
    target.mkdir(parents=True, exist_ok=True)
    if not (target / "naiwa.json").exists():
        # 清单文件作为完成标记，只在图片全部复制完成后写入。
        images = target / "images"
        images.mkdir(exist_ok=True)
        definitions = json.loads((resources / "naiwa.json").read_text("utf-8"))
        for item in definitions:
            source = resources / item["image"]
            # 内置素材为 WebP 以减小插件体积；转成 JPEG 保证 QQ 与各类图床都能直接使用。
            name = source.stem + ".jpg"
            with Image.open(source) as image:
                image.convert("RGB").save(images / name, "JPEG", quality=88)
            item["image"] = f"images/{name}"
        temp = target / "naiwa.json.tmp"
        temp.write_text(json.dumps(definitions, ensure_ascii=False, indent=2), "utf-8")
        temp.replace(target / "naiwa.json")


def read_catalog(data_dir: Path) -> list[dict]:
    root = (data_dir / "catalog").resolve()
    try:
        definitions = json.loads((root / "naiwa.json").read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise NaiwaError("图库 JSON 无法读取，原有收藏和有效图库均已保留。") from exc
    if not isinstance(definitions, list) or not definitions:
        raise NaiwaError("图库必须是非空列表。")
    archive = data_dir / "assets"
    archive.mkdir(parents=True, exist_ok=True)
    ids = set()
    validated = []
    for index, item in enumerate(definitions):
        if not isinstance(item, dict):
            raise NaiwaError(f"图库第 {index + 1} 项必须为对象。")
        item_id = item.get("id", "")
        if not isinstance(item_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", item_id):
            raise NaiwaError(f"图库第 {index + 1} 项 ID 不合法。")
        if item_id in ids:
            raise NaiwaError(f"图库存在重复 ID：{item_id}")
        ids.add(item_id)
        for key, low, limit in (
            ("name", 1, 40),
            ("description", 0, 40),
            ("analysis", 1, 600),
            ("group", 1, 20),
        ):
            if not isinstance(item.get(key), str) or not low <= len(item[key].strip()) <= limit:
                raise NaiwaError(f"{item_id} 的 {key} 必须是 {low}–{limit} 字的文本。")
        source_name = item.get("source", "")
        if not isinstance(source_name, str) or len(source_name) > 80:
            raise NaiwaError(f"{item_id} 的 source 必须是 80 字以内的文本。")
        enabled = item.get("enabled", True)
        order = item.get("sort_order", index)
        if type(enabled) is not bool or type(order) is not int:
            raise NaiwaError(f"{item_id} 的 enabled/sort_order 类型错误。")
        image_name = item.get("image", f"images/{item_id}.png")
        if not isinstance(image_name, str):
            raise NaiwaError(f"{item_id} 的图片路径必须为字符串。")
        path = (root / image_name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise NaiwaError(f"{item_id} 图片不存在或超出图库目录。")
        try:
            if path.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Image too large")
            with path.open("rb") as source:
                raw = source.read(10 * 1024 * 1024 + 1)
            if len(raw) > 10 * 1024 * 1024:
                raise ValueError("Image too large")
            suffix = path.suffix.lower()
            formats = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
            with Image.open(io.BytesIO(raw)) as img:
                if suffix not in {".png", ".jpg", ".jpeg", ".webp"} or img.format not in formats:
                    raise ValueError("Unsupported image format")
                # 后缀与真实格式不一致时，归档素材按真实格式命名，保证上传 MIME 类型正确。
                suffix = formats[img.format]
                if img.width * img.height > 16_000_000:
                    raise ValueError("Image dimensions too large")
                width, height = img.size
                img.verify()
            # verify() 不会解码 JPEG 像素，这里直接校验实际归档的字节。
            with Image.open(io.BytesIO(raw)) as img:
                img.load()
            digest = hashlib.sha256(raw).hexdigest()
            asset_name = f"{digest}{suffix}"
            dest = archive / asset_name
            if not dest.exists():
                temp = dest.with_suffix(dest.suffix + ".tmp")
                temp.write_bytes(raw)
                temp.replace(dest)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise NaiwaError(f"{item_id} 图片无法解析或超过限制。") from exc
        validated.append(
            {
                "id": item_id,
                "name": " ".join(item["name"].split()),
                "description": item["description"].strip(),
                "analysis": item["analysis"].strip(),
                "asset": asset_name,
                "enabled": enabled,
                "sort_order": order,
                "group_name": " ".join(item["group"].split()),
                "source": source_name.strip(),
                "width": width,
                "height": height,
            }
        )
    if not any(p["enabled"] for p in validated):
        raise NaiwaError("至少保留一件启用的奶娃；本次重载未生效。")
    return validated
