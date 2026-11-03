"""把 v1.1.0 之前的单文件图库拆成「官方名单 + 自定义图库」。"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..config import NaiwaError
from .fingerprint import SAME_IMAGE_DISTANCE, dhash, distance
from .merge import CUSTOM, LEGACY

TEXT_KEYS = ("name", "description", "analysis", "group", "source")


def same_image(root: Path, name, hashes: list[str]) -> bool | None:
    """与历史官方图比较；图片缺失或无法识别时返回 None，按未改动处理。"""
    if not isinstance(name, str):
        return None
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            value = dhash(image)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return min(distance(value, old) for old in hashes) <= SAME_IMAGE_DISTANCE


def migrate(data_dir: Path, resources: Path, official: tuple[dict, ...]) -> str:
    """返回迁移摘要；旧清单无法读取时抛出 NaiwaError，不做任何改动。"""
    root = (data_dir / "catalog").resolve()
    try:
        entries = json.loads((root / LEGACY).read_text("utf-8"))
        if not isinstance(entries, list):
            raise ValueError("Legacy catalog must be a list")
    except (OSError, ValueError) as exc:
        raise NaiwaError("旧版图库 naiwa.json 无法读取，未执行迁移，原有图库已保留。") from exc
    history = json.loads((resources / "legacy.json").read_text("utf-8"))
    official_ids = {item["id"] for item in official}

    custom, keep, drop, seen = [], set(), set(), set()
    counts = {"official": 0, "override": 0, "disabled": 0, "custom": 0}
    for index, entry in enumerate(entries):
        item_id = entry.get("id") if isinstance(entry, dict) else None
        old = history.get(item_id) if item_id in official_ids else None
        if old is None:
            # 管理员自己加的条目原样保留，字段是否有效交给图库校验。
            custom.append(entry)
            counts["custom"] += 1
            if isinstance(entry, dict) and isinstance(entry.get("image", ""), str):
                keep.add(entry.get("image", f"images/{item_id}.png"))
            continue
        seen.add(item_id)
        image = entry.get("image", f"images/{item_id}.png")
        override = {"id": item_id}
        for key in TEXT_KEYS:
            if key in entry and entry[key] not in old[key]:
                override[key] = entry[key]
        if entry.get("enabled", True) is not True:
            override["enabled"] = entry.get("enabled")
        order = entry.get("sort_order", index)
        if order not in old["sort_order"]:
            override["sort_order"] = order
        if same_image(root, image, old["dhash"]) is False:
            override["image"] = image
            keep.add(image)
        elif isinstance(image, str):
            drop.add(image)
        if len(override) == 1:
            counts["official"] += 1
        else:
            custom.append(override)
            counts["disabled" if override == {"id": item_id, "enabled": False} else "override"] += 1
    # 旧版删除整条记录就等于下架，迁移后不能让它重新出现。
    for item_id in history:
        if item_id in official_ids and item_id not in seen:
            custom.append({"id": item_id, "enabled": False})
            counts["disabled"] += 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / f"legacy-{stamp}"
    backup.mkdir()
    shutil.copy2(root / LEGACY, backup / LEGACY)
    if (root / "images").is_dir():
        shutil.copytree(root / "images", backup / "images")
    temp = root / f"{CUSTOM}.tmp"
    temp.write_text(json.dumps(custom, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temp.replace(root / CUSTOM)
    (root / LEGACY).unlink()
    # 只清理确认与官方一致、且没有被其他条目引用的旧图片副本。
    for name in drop - keep:
        path = (root / name).resolve()
        if path.parent == root / "images" and path.is_file():
            path.unlink()

    summary = (
        f"已迁移旧版图库：官方原样 {counts['official']} 件，覆盖 {counts['override']} 件，"
        f"下架 {counts['disabled']} 件，自定义新增 {counts['custom']} 件。"
        f"旧文件备份在 catalog/{backup.name}。"
    )
    (root / "迁移报告.txt").write_text(summary + "\n", "utf-8")
    return summary
