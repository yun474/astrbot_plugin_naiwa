"""合并官方名单与管理员的自定义图库，得到写入数据库的图库条目。"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import NaiwaError
from .fields import REQUIRED, check_id, clean
from .images import archive_image, archived_size

CUSTOM = "custom.json"
LEGACY = "naiwa.json"


@dataclass
class Catalog:
    items: list[dict]
    # 已启用但图片尚未下载、本次没有放进图库的官方条目。
    pending: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_custom(root: Path) -> list:
    path = root / CUSTOM
    if not path.exists():
        if (root / LEGACY).exists():
            raise NaiwaError("旧版图库尚未完成迁移，已保留原有图库，请查看插件日志。")
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise NaiwaError("自定义图库 custom.json 无法读取，原有收藏和有效图库均已保留。") from exc
    if not isinstance(data, list):
        raise NaiwaError("自定义图库 custom.json 必须是列表。")
    return data


def custom_image(root: Path, archive: Path, name, item_id: str) -> tuple[str, int, int]:
    if not isinstance(name, str):
        raise NaiwaError(f"{item_id} 的图片路径必须为字符串。")
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NaiwaError(f"{item_id} 图片不存在或超出图库目录。")
    return archive_image(path, archive, item_id)


def build_catalog(
    data_dir: Path, official: tuple[dict, ...], current: dict[str, str] | None = None
) -> Catalog:
    """current 为数据库里各条目正在使用的素材，官方新图下载完成前继续沿用。"""
    root = (data_dir / "catalog").resolve()
    archive = data_dir / "assets"
    archive.mkdir(parents=True, exist_ok=True)
    current = current or {}
    official_ids = {item["id"] for item in official}
    overrides, extras, warnings, ids = {}, [], [], set()
    for index, entry in enumerate(load_custom(root)):
        if not isinstance(entry, dict):
            raise NaiwaError(f"自定义图库第 {index + 1} 项必须为对象。")
        item_id = check_id(entry.get("id"), f"自定义图库第 {index + 1} 项")
        if item_id in ids:
            raise NaiwaError(f"自定义图库存在重复 ID：{item_id}")
        ids.add(item_id)
        if item_id in official_ids:
            overrides[item_id] = entry
            continue
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            # 多半是覆盖的官方条目已被移除；不能因此卡住整个图库的更新。
            warnings.append(
                f"自定义条目 {item_id} 不是官方条目且缺少 {'、'.join(missing)}，已忽略。"
            )
            continue
        extras.append(entry)

    items, pending = [], []
    for spec in official:
        item_id = spec["id"]
        entry = overrides.get(item_id, {})
        fields = {
            key: spec[key]
            for key in ("name", "description", "analysis", "group_name", "source", "enabled")
        }
        fields["sort_order"] = spec["sort_order"]
        fields.update(clean(entry, item_id, partial=True))
        if "image" in entry:
            asset, width, height = custom_image(root, archive, entry["image"], item_id)
        else:
            asset, size = spec["asset"], archived_size(archive, spec["asset"])
            if size is None and item_id in current:
                asset, size = current[item_id], archived_size(archive, current[item_id])
            if size is None:
                if fields["enabled"]:
                    pending.append(item_id)
                continue
            width, height = size
        items.append({"id": item_id, **fields, "asset": asset, "width": width, "height": height})

    # 自定义新增条目默认排在官方条目之后，按 custom.json 中的顺序排列。
    base = max((spec["sort_order"] for spec in official), default=-1) + 1
    for index, entry in enumerate(extras):
        item_id = entry["id"]
        fields = {"enabled": True, "sort_order": base + index, **clean(entry, item_id)}
        image = entry.get("image", f"images/{item_id}.png")
        asset, width, height = custom_image(root, archive, image, item_id)
        items.append({"id": item_id, **fields, "asset": asset, "width": width, "height": height})

    if not any(item["enabled"] for item in items):
        raise NaiwaError("至少保留一件启用的奶蛙；本次重载未生效。")
    return Catalog(items, pending, warnings)
