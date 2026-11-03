"""随插件分发的官方名单：记录官方条目、每张图的指纹和对应的 Release 图包。"""

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..config import NaiwaError
from .fields import check_id, clean

SHA256 = re.compile(r"[0-9a-f]{64}")
PACK_IMAGE = re.compile(r"images/[a-z0-9][a-z0-9_-]{0,63}\.(jpg|png)")


@dataclass(frozen=True)
class Pack:
    tag: str
    file: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Official:
    pack: Pack
    items: tuple[dict, ...]


def load_official(resources: Path) -> Official:
    try:
        data = json.loads((resources / "naiwa.json").read_text("utf-8"))
        pack = Pack(**data["pack"])
        definitions = data["items"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise NaiwaError("内置官方名单损坏，请重新安装插件。") from exc
    if (
        not isinstance(pack.size, int)
        or not SHA256.fullmatch(str(pack.sha256))
        or not all(isinstance(v, str) and v for v in (pack.tag, pack.file))
    ):
        raise NaiwaError("内置官方名单的图包信息无效。")
    items, ids = [], set()
    for index, item in enumerate(definitions):
        item_id = check_id(item.get("id"), f"官方名单第 {index + 1} 项")
        if item_id in ids:
            raise NaiwaError(f"官方名单存在重复 ID：{item_id}")
        ids.add(item_id)
        image, digest = item.get("image"), item.get("sha256")
        if not isinstance(image, str) or not PACK_IMAGE.fullmatch(image):
            raise NaiwaError(f"官方条目 {item_id} 的图片路径无效。")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise NaiwaError(f"官方条目 {item_id} 的图片指纹无效。")
        fields = {"enabled": True, "sort_order": index, **clean(item, item_id)}
        items.append(
            {
                "id": item_id,
                **fields,
                "image": image,
                "sha256": digest,
                # 官方图解包后直接按字节指纹存入 assets/，与自定义图片的归档规则一致。
                "asset": digest + PurePosixPath(image).suffix,
            }
        )
    if not items:
        raise NaiwaError("内置官方名单为空。")
    return Official(pack, tuple(items))
