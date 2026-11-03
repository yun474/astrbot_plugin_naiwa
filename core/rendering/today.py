"""今日卡片：画框展品加居中展签。"""

import re
from pathlib import Path

from PIL import Image

from .base import (
    BASE,
    BODY,
    CREAM,
    DIM_GOLD,
    FRAME_LINE,
    GREEN,
    INNER,
    OVERLAY0,
    OVERLAY2,
    PAD,
    SOURCES,
    SURFACE0,
    SURFACE1,
    WIDTH,
    YELLOW,
    YELLOW_L,
    Canvas,
    Card,
    finish,
    load_art,
)

ART_MAX = (INNER - 36, 720)
FRAME_PAD = 18
FRAME_TOP = 232


def exhibit_label(item: dict) -> str:
    """展签行：原版只写「原版」，其余写分组与编号。"""
    group = item.get("group_name") or ""
    if group == "原版":
        return group
    number = re.search(r"(\d+)$", item["id"])
    return f"{group}  ·  第 {int(number.group(1))} 号" if number else group


def short_day(day: str) -> str:
    _, month, date = day.split("-")
    return f"{int(month)}月{int(date)}日"


def render_today(
    root: Path, result: dict, progress: dict, state: str, protection: str, fresh: bool
) -> Card:
    item = result["item"]
    art = load_art(root, item["asset"])
    scale = min(ART_MAX[0] / art.width, ART_MAX[1] / art.height)
    art = art.resize(
        (max(1, round(art.width * scale)), max(1, round(art.height * scale))),
        Image.Resampling.LANCZOS,
    )
    description = " ".join(item.get("description", "").split())
    probe = Canvas(root, 1, 1)
    lines = probe.wrap(" ".join(item["analysis"].split()), 32, INNER - 80)
    probe.image.close()

    frame_h = art.height + FRAME_PAD * 2
    label_top = FRAME_TOP + frame_h + 64
    name_top = label_top + 48
    ornament = name_top + (138 if description else 104)
    text_top = ornament + 42
    stats_top = text_top + len(lines) * 54 + 48
    stats_h = 232
    footer = stats_top + stats_h + 52
    canvas = Canvas(root, WIDTH, footer + 48)
    canvas.glow((WIDTH // 2, FRAME_TOP + frame_h // 2), max(art.width, art.height) * 0.6, 34)

    canvas.text("今日奶娃", (PAD - 4, 60), 80, YELLOW_L, 800)
    canvas.text(short_day(result["day"]), (WIDTH - PAD, 128), 26, OVERLAY2, 500, "rs")

    # 画框：投影、金边与内衬细线
    frame_w = art.width + FRAME_PAD * 2
    fx = (WIDTH - frame_w) // 2
    canvas.shadow((fx + 6, FRAME_TOP, fx + frame_w - 6, FRAME_TOP + frame_h), 28, 22, 200, 24)
    canvas.draw.rounded_rectangle(
        (fx, FRAME_TOP, fx + frame_w, FRAME_TOP + frame_h),
        radius=26,
        fill=SURFACE1,
        outline=YELLOW,
        width=3,
    )
    canvas.draw.rounded_rectangle(
        (fx + 9, FRAME_TOP + 9, fx + frame_w - 9, FRAME_TOP + frame_h - 9),
        radius=19,
        outline=FRAME_LINE,
        width=1,
    )
    canvas.paste(art, (fx + FRAME_PAD, FRAME_TOP + FRAME_PAD), 14)
    art.close()

    # 斜挂在画框左上角的绶带：新收集为绿色，其余为奶黄
    face = canvas.font(28, 800)
    ribbon_w = int(canvas.draw.textlength(state, font=face) + 96)
    ribbon_h = face.size + 26
    rx, ry = fx - 14, FRAME_TOP - 26
    canvas.shadow((rx, ry, rx + ribbon_w, ry + ribbon_h), ribbon_h // 2, 10, 150, 6)
    canvas.draw.rounded_rectangle(
        (rx, ry, rx + ribbon_w, ry + ribbon_h),
        radius=ribbon_h // 2,
        fill=GREEN if fresh else YELLOW,
    )
    canvas.text(state, (rx + ribbon_w / 2, ry + ribbon_h / 2), 28, BASE, 800, "mm")

    # 展签：分组与编号、名字、小标题、分隔饰线、签语
    cx = WIDTH // 2
    canvas.text(exhibit_label(item), (cx, label_top), 24, YELLOW, 600, "mm", width=INNER)
    canvas.text(item["name"], (cx, name_top), 60, CREAM, 800, "mt", width=INNER)
    if description:
        canvas.text(description, (cx, name_top + 86), 28, YELLOW_L, 500, "mt", width=INNER)
    canvas.draw.line((cx - 150, ornament, cx - 18, ornament), fill=DIM_GOLD, width=2)
    canvas.draw.line((cx + 18, ornament, cx + 150, ornament), fill=DIM_GOLD, width=2)
    canvas.draw.polygon(
        [(cx, ornament - 8), (cx + 8, ornament), (cx, ornament + 8), (cx - 8, ornament)],
        fill=YELLOW,
    )
    body = canvas.font(32)
    for index, line in enumerate(lines):
        canvas.draw.text((cx, text_top + index * 54), line, font=body, fill=BODY, anchor="mt")

    # 统计
    canvas.draw.rounded_rectangle(
        (PAD, stats_top, WIDTH - PAD, stats_top + stats_h), radius=28, fill=SURFACE0
    )
    column = INNER / 3
    for index, (label, value, unit) in enumerate(
        (
            ("本件累计", str(result["count"]), "次"),
            ("累计收获", str(progress["total"]), "件"),
            ("已解锁", str(progress["unlocked"]), f"/ {progress['active_total']}"),
        )
    ):
        center = PAD + column * index + column / 2
        canvas.text(label, (center, stats_top + 32), 22, OVERLAY2, 500, "mt")
        value_face, unit_face = canvas.font(52, 800), canvas.font(24, 500)
        value_w = canvas.draw.textlength(value, font=value_face)
        unit_w = canvas.draw.textlength(unit, font=unit_face)
        start = center - (value_w + 8 + unit_w) / 2
        canvas.draw.text((start, stats_top + 120), value, font=value_face, fill=YELLOW_L, anchor="ls")
        canvas.draw.text(
            (start + value_w + 8, stats_top + 120), unit, font=unit_face, fill=OVERLAY2, anchor="ls"
        )
        if index:
            x = PAD + column * index
            canvas.draw.line((x, stats_top + 38, x, stats_top + 116), fill=SURFACE1, width=2)
    total = progress["active_total"]
    ratio = min(progress["unlocked"] / total, 1) if total else 0
    canvas.progress(PAD + 40, WIDTH - PAD - 130, stats_top + 158, ratio)
    canvas.text(f"{ratio:.1%}", (WIDTH - PAD - 40, stats_top + 165), 24, GREEN, 800, "rm")
    if protection:
        canvas.text(protection, (PAD + 40, stats_top + 196), 21, OVERLAY2, width=INNER - 80)

    source = SOURCES.get(item.get("source", ""), item.get("source", ""))
    if source:
        canvas.text(f"图源：{source}", (cx, footer), 20, OVERLAY0, anchor="mm", width=INNER)
    return finish(canvas.image)
