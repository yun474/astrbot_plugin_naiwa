import asyncio
import math
import re
from pathlib import Path

from .config import NaiwaError, Settings
from .delivery import Message
from .rendering import (
    ATLAS_SHEET_SIZE,
    PEN_SHEET_SIZE,
    render_collection,
    render_ranking,
    render_today,
)


def md(text: str) -> str:
    text = str(text).replace("{{", "｛｛").replace("}}", "｝｝")
    return re.sub(r"([\\`*_{}\[\]<>()#+.!|~>-])", r"\\\1", text)


def display_name(user: dict) -> str:
    return user.get("alias") or user.get("nickname") or f"玩家 {user['id']:04d}"


def paginate(items: list, page: int, size: int) -> tuple[list, int, int]:
    pages = max(1, math.ceil(len(items) / size))
    if not 1 <= page <= pages:
        raise NaiwaError(f"页码超出范围，请输入 1–{pages}。")
    return items[(page - 1) * size : page * size], page, pages


def keyboard(
    settings: Settings, owner: str, command: str = "", page: int = 1, pages: int = 1
) -> dict:
    def button(label: str, data: str, private: bool = False):
        permission = {"type": 0, "specify_user_ids": [owner]} if private else {"type": 2}
        return {
            "id": data,
            "render_data": {"label": label, "visited_label": label, "style": 1},
            "action": {
                "type": 2,
                "permission": permission,
                "data": settings.command_prefix + data,
            },
        }

    rows = [
        {"buttons": [button("今日奶蛙", "今日奶蛙"), button("奶蛙图鉴", "奶蛙图鉴")]},
        {"buttons": [button("奶蛙排行", "奶蛙排行"), button("我的展柜", "我的展柜")]},
    ]
    navigation = []
    if page > 1:
        navigation.append(button("上一页", f"{command} {page - 1}", True))
    if page < pages:
        navigation.append(button("下一页", f"{command} {page + 1}", True))
    if navigation:
        rows.append({"buttons": navigation})
    return {"content": {"rows": rows}}


def image_size(item: dict, long_side: int = 640) -> tuple[int, int]:
    """Markdown 图片按原图比例显示，长边固定。"""
    width, height = item.get("width") or 0, item.get("height") or 0
    if width <= 0 or height <= 0:
        return long_side, long_side
    scale = long_side / max(width, height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def today_message(
    settings: Settings, root: Path, user: dict, result: dict, progress: dict
) -> Message:
    item = result["item"]
    fresh = result["created"] and result["new_species"]
    state = (
        "今天已经抽过啦"
        if not result["created"]
        else "新收集！"
        if fresh
        else f"第 {result['count']} 次相遇"
    )
    protection = ""
    streak = result.get("repeat_streak", 0)
    if settings.duplicate_pity and streak and progress["unlocked"] < progress["active_total"]:
        protection = (
            "下次领取必出未收集奶蛙！"
            if streak >= settings.duplicate_pity
            else f"重复保护 {streak}/{settings.duplicate_pity}"
        )

    def local() -> Message:
        card = render_today(
            root,
            result,
            progress,
            "今日已领取" if not result["created"] else state,
            protection,
            fresh,
        )
        return Message("", (card.data,), local=True)

    if not settings.use_host("draw"):
        return local()
    # 小标题为空时，引用块里只放签语。
    quote = "\n\n".join(part for part in (item["description"], item["analysis"]) if part.strip())
    description = "\n".join(f"> {line}" if line else ">" for line in md(quote).splitlines())
    width, height = image_size(item)
    group = item.get("group_name") or ""
    title = f"**{md(item['name'])}**" + (f" · {md(group)}" if group else "")
    text = (
        f'<qqbot-at-user id="{user["open_id"]}" />\n\n### 今日奶蛙 · {state}\n\n'
        f"{title}\n\n"
        f"![奶蛙 #{width}px #{height}px]({{{{image:0}}}})\n\n"
        f"{description}\n\n"
        f"本件累计 **{result['count']}** 次 · 总收获 **{progress['total']}** 件\n\n"
        f"已解锁 **{progress['unlocked']}/{progress['active_total']}** · {result['day']}"
    )
    if protection:
        text += f"\n\n{protection}"
    return Message(
        text,
        (root / "assets" / item["asset"],),
        keyboard(settings, user["open_id"]),
        fallback=local,
    )


async def collection_message(
    settings: Settings, root: Path, user: dict, progress: dict, page: int, atlas: bool
) -> Message:
    """两种发送模式共用同一张内存中的卡片。"""
    title = "奶蛙图鉴" if atlas else "我的展柜"
    items = (
        [p for p in progress["entries"] if p["enabled"]]
        if atlas
        else [p for p in progress["entries"] if p["count"]]
    )
    entries, page, pages = paginate(items, page, ATLAS_SHEET_SIZE if atlas else PEN_SHEET_SIZE)
    card = await asyncio.to_thread(
        render_collection, root, display_name(user), progress, entries, page, pages, atlas
    )
    return card_message(settings, user, card, title, "atlas" if atlas else "pen", page, pages)


def ranking_message(
    settings: Settings, root: Path, user: dict, boards: dict, avatars: dict
) -> Message:
    return card_message(
        settings, user, render_ranking(root, boards, avatars), "奶蛙排行榜", "ranking"
    )


def card_message(settings, user, card, title, command, page=1, pages=1):
    hosted = settings.use_host(command)
    return Message(
        f"![{title} #{card.width}px #{card.height}px]({{{{image:0}}}})" if hosted else "",
        (card.data,),
        keyboard(settings, user["open_id"], title, page, pages) if hosted else None,
        local=not hosted,
        fallback=(lambda: Message("", (card.data,), local=True)) if hosted else None,
    )


def material_message(usage: dict, active: bool, cache_minutes: int) -> Message:
    cleanup = "插件会定期自动清理" if active else "当前未选用 QQ 素材库，插件不会自动清理"
    cache = f"{cache_minutes} 分钟" if cache_minutes else "即用即删"
    return Message(
        f"QQ 素材库占用：{usage['total']}/100\n"
        f"本插件：{usage['ours']} 张，其中缓存中的奶蛙图 {usage['cached']} 张（缓存时间：{cache}）\n"
        f"超过 10 分钟的残留：{usage['stale']} 张，{cleanup}\n"
        f"其他插件或手动上传：{usage['others']} 张\n"
        "可发送「奶蛙素材库 删除缓存」或「奶蛙素材库 删除全部」清理。"
    )


def purge_message(result: dict, everything: bool) -> Message:
    scope = "整个素材库（含其他插件的素材）" if everything else "本插件的素材"
    text = f"已清理{scope}：删除 {result['deleted']} 张"
    if result["skipped"]:
        text += f"，跳过正在发送的 {result['skipped']} 张"
    if result["failed"]:
        text += f"，{result['failed']} 张删除失败，请稍后重试"
    return Message(text + "。")
