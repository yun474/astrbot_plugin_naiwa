"""启动时准备图库目录：放入兜底图、迁移旧版图库并导出只读官方名单。"""

import hashlib
import json
from pathlib import Path

from .images import store
from .merge import CUSTOM, LEGACY
from .migrate import migrate

READONLY = "official.readonly.json"


def install_fallback(resources: Path, archive: Path):
    """随插件分发的兜底图与图包内字节一致，按同样的指纹命名放入归档。"""
    for path in sorted((resources / "fallback").glob("*")):
        raw = path.read_bytes()
        store(archive / f"{hashlib.sha256(raw).hexdigest()}{path.suffix.lower()}", raw)


def export_official(root: Path, official: tuple[dict, ...]):
    data = {
        "说明": "此文件由插件在每次启动时生成，修改无效。自定义请编辑同目录的 custom.json。",
        "items": [
            {
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "analysis": item["analysis"],
                "group": item["group_name"],
                "source": item["source"],
                "enabled": item["enabled"],
                "sort_order": item["sort_order"],
            }
            for item in official
        ],
    }
    temp = root / f"{READONLY}.tmp"
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temp.replace(root / READONLY)


def prepare(data_dir: Path, resources: Path, official: tuple[dict, ...]) -> str | None:
    """返回迁移摘要（没有迁移时为 None）；旧清单无法迁移时抛出 NaiwaError。"""
    root = data_dir / "catalog"
    (root / "images").mkdir(parents=True, exist_ok=True)
    archive = data_dir / "assets"
    archive.mkdir(parents=True, exist_ok=True)
    (data_dir / "packs").mkdir(exist_ok=True)
    install_fallback(resources, archive)
    export_official(root, official)
    summary = None
    if (root / LEGACY).exists() and not (root / CUSTOM).exists():
        summary = migrate(data_dir, resources, official)
    # 必须在迁移检查之后创建，否则旧清单永远不会被迁移。
    if not (root / CUSTOM).exists() and not (root / LEGACY).exists():
        (root / CUSTOM).write_text("[]\n", "utf-8")
    return summary
