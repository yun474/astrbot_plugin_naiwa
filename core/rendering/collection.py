"""奶娃图鉴与我的展柜。"""

import math
from pathlib import Path

from .base import (
    CREAM,
    DIM_GOLD,
    FRAME_LINE,
    GREEN,
    INNER,
    OVERLAY2,
    PAD,
    SURFACE0,
    SURFACE1,
    WIDTH,
    YELLOW,
    YELLOW_L,
    Canvas,
    Card,
    finish,
    thumbnail,
)

# 单页上限确保整页 PNG 不超过发送限制：图鉴是小方格，展柜是照片卡片。
ATLAS_SHEET_SIZE = 192
PEN_SHEET_SIZE = 48
ATLAS_COLUMNS, ATLAS_TILE, ATLAS_GAP, ATLAS_TOP = 8, 108, 12, 372
PEN_COLUMNS, PEN_W, PEN_H, PEN_GAP, PEN_TOP = 4, 222, 262, 20, 470


def footer(canvas: Canvas, y: int, note: str, page: int, pages: int):
    canvas.draw.line((PAD, y, WIDTH - PAD, y), fill=SURFACE1, width=2)
    canvas.text(note, (PAD, y + 38), 20, OVERLAY2, anchor="lm")
    canvas.text(f"{page:02d} / {pages:02d}", (WIDTH - PAD, y + 38), 24, YELLOW_L, 800, "rm")


def render_collection(
    root: Path, name: str, progress: dict, entries: list[dict], page: int, pages: int, atlas: bool
) -> Card:
    """图鉴格子不显示名称，未解锁的只画问号，不读取对应素材。"""
    total = progress["active_total"]
    unlocked = progress["unlocked"]
    ratio = min(unlocked / total, 1) if total else 0
    columns = ATLAS_COLUMNS if atlas else PEN_COLUMNS
    rows = max(1, math.ceil(len(entries) / columns))
    if atlas:
        step_x, step_y, top = ATLAS_TILE + ATLAS_GAP, ATLAS_TILE + ATLAS_GAP, ATLAS_TOP
        left = (WIDTH - (columns * ATLAS_TILE + (columns - 1) * ATLAS_GAP)) // 2
    else:
        step_x, step_y, top = PEN_W + PEN_GAP, PEN_H + PEN_GAP, PEN_TOP
        left = (WIDTH - (columns * PEN_W + (columns - 1) * PEN_GAP)) // 2
    bottom = top + rows * step_y + 10
    canvas = Canvas(root, WIDTH, bottom + 86)
    canvas.header("奶娃图鉴" if atlas else "我的展柜", name)

    if atlas:
        canvas.draw.rounded_rectangle((PAD, 196, WIDTH - PAD, 316), radius=28, fill=SURFACE0)
        canvas.text("已解锁", (PAD + 36, 226), 24, OVERLAY2, 500)
        canvas.text(f"{unlocked} / {total}", (PAD + 132, 214), 42, YELLOW_L, 800)
        canvas.text(f"{ratio:.1%}", (WIDTH - PAD - 36, 240), 32, GREEN, 800, "rm")
        canvas.progress(PAD + 36, WIDTH - PAD - 36, 278, ratio, 12)
    else:
        canvas.draw.rounded_rectangle((PAD, 196, WIDTH - PAD, 392), radius=28, fill=SURFACE0)
        column = INNER / 3
        for index, (label, value) in enumerate(
            (
                ("已解锁种类", f"{unlocked} / {total}"),
                ("累计收获", f"{progress['total']} 件"),
                ("收集进度", f"{ratio:.1%}"),
            )
        ):
            center = PAD + column * index + column / 2
            canvas.text(label, (center, 226), 22, OVERLAY2, 500, "mt")
            canvas.text(value, (center, 262), 42, YELLOW_L, 800, "mt", width=column - 24)
            if index:
                x = PAD + column * index
                canvas.draw.line((x, 232, x, 310), fill=SURFACE1, width=2)
        canvas.progress(PAD + 40, WIDTH - PAD - 40, 346, ratio, 12)
        canvas.text("收藏的奶娃", (PAD, 428), 28, CREAM, 800, "lm")
        canvas.text(f"共 {progress['species']} 种", (WIDTH - PAD, 428), 22, OVERLAY2, anchor="rm")

    for index, entry in enumerate(entries):
        x = left + (index % columns) * step_x
        y = top + (index // columns) * step_y
        if atlas:
            box = (x, y, x + ATLAS_TILE, y + ATLAS_TILE)
            if not entry["count"]:
                canvas.draw.rounded_rectangle(box, radius=18, fill=SURFACE0, outline=SURFACE1, width=2)
                canvas.text("?", (x + ATLAS_TILE / 2, y + ATLAS_TILE / 2), 52, DIM_GOLD, 800, "mm")
                continue
            canvas.draw.rounded_rectangle(box, radius=18, fill=SURFACE1, outline=FRAME_LINE, width=2)
            art = thumbnail(root, entry["asset"], (ATLAS_TILE - 8, ATLAS_TILE - 8))
            canvas.paste(art, (x + 4, y + 4), 14)
            art.close()
            continue
        canvas.draw.rounded_rectangle(
            (x, y, x + PEN_W, y + PEN_H), radius=22, fill=SURFACE0, outline=SURFACE1, width=2
        )
        art = thumbnail(root, entry["asset"], (PEN_W - 24, 162))
        canvas.paste(art, (x + 12, y + 12), 14)
        art.close()
        canvas.draw.rounded_rectangle(
            (x + 12, y + 12, x + PEN_W - 12, y + 174), radius=14, outline=FRAME_LINE, width=1
        )
        # 长名字先缩小字号，仍放不下再截断，避免同系列名字截成一样。
        name, size = " ".join(entry["name"].split()), 24
        while size > 18 and canvas.draw.textlength(name, font=canvas.font(size, 700)) > PEN_W - 24:
            size -= 1
        canvas.text(name, (x + PEN_W / 2, y + 204), size, CREAM, 700, "mm", width=PEN_W - 24)
        count = f"× {entry['count']}" + (" · 已下架" if not entry["enabled"] else "")
        canvas.text(count, (x + PEN_W / 2, y + 228), 20, YELLOW, 700, "mt", width=PEN_W - 24)

    if not entries:
        message = "暂无可展示的奶娃" if atlas else "展柜还是空的，先抽一只今日奶娃吧。"
        canvas.text(message, (WIDTH / 2, top + 70), 26, OVERLAY2, anchor="mm")
    footer(
        canvas,
        bottom,
        "彩色 · 已解锁    问号 · 待发现" if atlas else "历史收藏会保留",
        page,
        pages,
    )
    return finish(canvas.image)
