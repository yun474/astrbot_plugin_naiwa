"""图库条目的字段校验，官方名单与自定义图库共用同一套规则。"""

import re

from ..config import NaiwaError

ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
TEXT_FIELDS = (("name", 1, 40), ("description", 0, 40), ("analysis", 1, 600), ("group", 1, 20))
REQUIRED = ("name", "description", "analysis", "group")


def check_id(item_id, label: str) -> str:
    if not isinstance(item_id, str) or not ID_PATTERN.fullmatch(item_id):
        raise NaiwaError(f"{label} ID 不合法。")
    return item_id


def clean(item: dict, item_id: str, *, partial: bool = False) -> dict:
    """校验并规整条目字段；partial 为真时只处理出现的字段，用于覆盖官方条目。"""
    fields = {}
    for key, low, limit in TEXT_FIELDS:
        if partial and key not in item:
            continue
        value = item.get(key)
        if not isinstance(value, str) or not low <= len(value.strip()) <= limit:
            raise NaiwaError(f"{item_id} 的 {key} 必须是 {low}–{limit} 字的文本。")
        if key == "name":
            fields["name"] = " ".join(value.split())
        elif key == "group":
            fields["group_name"] = " ".join(value.split())
        else:
            fields[key] = value.strip()
    if not partial or "source" in item:
        source = item.get("source", "")
        if not isinstance(source, str) or len(source) > 80:
            raise NaiwaError(f"{item_id} 的 source 必须是 80 字以内的文本。")
        fields["source"] = source.strip()
    for key, kind in (("enabled", bool), ("sort_order", int)):
        if key in item:
            if type(item[key]) is not kind:
                raise NaiwaError(f"{item_id} 的 enabled/sort_order 类型错误。")
            fields[key] = item[key]
    return fields
