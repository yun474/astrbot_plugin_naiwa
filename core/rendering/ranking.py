"""奶蛙排行榜：种类榜与数量榜并排。"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .base import (
    BASE,
    CREAM,
    MEDALS,
    OVERLAY2,
    PAD,
    SURFACE0,
    SURFACE1,
    YELLOW,
    Canvas,
    Card,
    finish,
    mix,
)

RANK_WIDTH = 1488
ROW = 100


def render_ranking(root: Path, boards: dict, avatars: dict[str, bytes]) -> Card:
    """两个前十榜单放在同一张图中；昵称和头像共用一个胶囊框。"""
    rows = max(1, *(len(boards[k][:10]) for k in ("species", "total")))
    canvas = Canvas(root, RANK_WIDTH, 300 + rows * ROW + 96)
    height = canvas.image.height
    canvas.header("奶蛙排行榜", "本群玩家 · 跨群累计（含下架收藏）")
    for column, (kind, label, unit) in enumerate(
        (("species", "收集种类榜", "种"), ("total", "累计数量榜", "件"))
    ):
        x = 48 + column * 704
        canvas.draw.rounded_rectangle((x, 196, x + 688, height - 72), radius=28, fill=SURFACE0)
        canvas.text(label, (x + 32, 236), 30, CREAM, 800, "lm")
        canvas.text("前十", (x + 656, 236), 22, YELLOW, 700, "rm")
        players = boards[kind][:10]
        if not players:
            canvas.text("还没有玩家上榜", (x + 32, 320), 26, OVERLAY2, anchor="lm")
        for index, player in enumerate(players):
            y = 284 + index * ROW
            color = MEDALS.get(player["rank"], OVERLAY2)
            canvas.text(f"{player['rank']:02d}", (x + 56, y + 40), 30, color, 800, "mm")
            canvas.draw.rounded_rectangle((x + 96, y + 4, x + 510, y + 76), radius=36, fill=SURFACE1)
            name = player.get("alias") or player.get("nickname") or f"玩家 {player['id']:04d}"
            avatar = avatars.get(player.get("open_id", ""))
            if avatar:
                with Image.open(io.BytesIO(avatar)) as source:
                    art = ImageOps.fit(source.convert("RGB"), (56, 56))
                mask = Image.new("L", (56, 56))
                ImageDraw.Draw(mask).ellipse((0, 0, 55, 55), fill=255)
                canvas.image.paste(art, (x + 104, y + 12), mask)
                canvas.refresh()
                art.close()
                mask.close()
            else:
                canvas.draw.ellipse((x + 104, y + 12, x + 160, y + 68), fill=mix(SURFACE1, YELLOW, 0.5))
                canvas.text(name[:1], (x + 132, y + 40), 26, BASE, 800, "mm")
            canvas.text(name, (x + 176, y + 40), 25, CREAM, 700, "lm", width=316)
            canvas.text(f"{player[kind]} {unit}", (x + 656, y + 40), 30, color, 800, "rm", width=140)
    canvas.text("每天领一只奶蛙，把日子攒成一座展馆。", (PAD, height - 38), 20, OVERLAY2, anchor="lm")
    return finish(canvas.image)
