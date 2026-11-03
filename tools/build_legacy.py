"""从 git 历史生成迁移用的历史官方指纹表 resources/legacy.json。

用法：
    python tools/build_legacy.py 提交1 [提交2 ...]

只需收录 v1.1.0 之前、内置单文件图库的版本；之后的版本不再产生旧版图库。
"""

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.catalog.fingerprint import dhash  # noqa: E402

FIELDS = ("name", "description", "analysis", "group", "source")


def show(rev: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, check=True
    ).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("revisions", nargs="+")
    args = parser.parse_args()

    table = {}
    for rev in args.revisions:
        for index, item in enumerate(json.loads(show(rev, "resources/naiwa.json"))):
            entry = table.setdefault(
                item["id"], {key: [] for key in (*FIELDS, "sort_order", "dhash")}
            )
            with Image.open(io.BytesIO(show(rev, f"resources/{item['image']}"))) as image:
                values = {
                    **{key: item.get(key, "") for key in FIELDS},
                    "sort_order": item.get("sort_order", index),
                    "dhash": dhash(image),
                }
            for key, value in values.items():
                if value not in entry[key]:
                    entry[key].append(value)
    (ROOT / "resources" / "legacy.json").write_text(
        json.dumps(table, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8", newline="\n"
    )
    print(f"已收录 {len(table)} 件历史官方条目")


if __name__ == "__main__":
    main()
