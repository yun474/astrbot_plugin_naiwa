"""各界面共用的配色、字体与绘制工具。"""

import hashlib
import io
import lzma
import shutil
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# 配色取自 NaiLoong-Universe palette.json 的 nailoongDark。
BASE = (18, 18, 18)
SURFACE0 = (31, 26, 15)
SURFACE1 = (46, 37, 17)
OVERLAY0 = (122, 111, 90)
OVERLAY2 = (156, 142, 122)
YELLOW = (255, 213, 79)
YELLOW_L = (255, 224, 130)
GREEN = (102, 187, 106)
CREAM = (245, 236, 215)
BODY = (222, 210, 184)
MEDALS = {1: (255, 200, 60), 2: (190, 200, 210), 3: (205, 140, 95)}

WIDTH = 1080
PAD = 64
INNER = WIDTH - PAD * 2
SOURCES = {
    "Nailong-Studio/NaiLoong-Universe": "奶蛙艺术圣殿",
    "GeorgeNaNN/nailong-memes": "nailong-memes",
}
# 这些标点不放在行首，换行时连同前一个字一起移到下一行。
NO_LINE_START = "，。、：；！？」』）—…"
FONT = Path(__file__).resolve().parents[2] / "resources" / "fonts" / "NotoSansSC.ttf.xz"
_FONT_LOCK = threading.Lock()


def mix(a: tuple, b: tuple, t: float) -> tuple:
    """在不透明画布上预先混色，代替半透明填充。"""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


DIM_GOLD = mix(BASE, YELLOW, 0.35)
FRAME_LINE = mix(SURFACE1, YELLOW, 0.35)


@lru_cache(maxsize=1)
def _font_digest() -> str:
    return hashlib.sha256(FONT.read_bytes()).hexdigest()[:16]


def font_path(root: Path) -> Path:
    """将内置字体一次性解压到插件数据目录，保留全部字形和字重。"""
    path = root / "fonts" / f"NotoSansSC-{_font_digest()}.ttf"
    with _FONT_LOCK:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            try:
                with lzma.open(FONT, "rb") as source, temp.open("wb") as output:
                    shutil.copyfileobj(source, output)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
    return path


@dataclass(frozen=True)
class Card:
    data: bytes
    width: int
    height: int


def finish(image: Image.Image) -> Card:
    with image, io.BytesIO() as output:
        image.convert("RGB").save(output, "PNG", optimize=True)
        return Card(output.getvalue(), image.width, image.height)


class Canvas:
    """暖黑底画布：顶部带一层暖棕渐变。"""

    def __init__(self, root: Path, width: int, height: int):
        self.root = root
        self.image = Image.new("RGBA", (width, height), (*BASE, 255))
        warm = Image.new("RGBA", (width, height), (*SURFACE0, 255))
        fade = Image.linear_gradient("L").resize((width, height))
        warm.putalpha(fade.point(lambda v: int((255 - v) * 0.75)))
        self.image.alpha_composite(warm)
        self.draw = ImageDraw.Draw(self.image)
        self.fonts = {}
        self.font_file = font_path(root)

    def font(self, size: int, weight: int = 400):
        if (size, weight) not in self.fonts:
            face = ImageFont.truetype(str(self.font_file), size)
            face.set_variation_by_axes([weight])
            self.fonts[size, weight] = face
        return self.fonts[size, weight]

    def refresh(self):
        """粘贴或合成图层后重新取得绘图对象。"""
        self.draw = ImageDraw.Draw(self.image)

    def text(self, value, xy, size, color, weight=400, anchor="la", width=None):
        # 名称等标签一律单行显示，超宽时截断。
        value = " ".join(str(value).split())
        face = self.font(size, weight)
        if width is not None and self.draw.textlength(value, font=face) > width:
            while value and self.draw.textlength(value + "…", font=face) > width:
                value = value[:-1]
            value += "…"
        self.draw.text(xy, value, font=face, fill=color, anchor=anchor)

    def wrap(self, text: str, size: int, width: int) -> list[str]:
        face = self.font(size)
        lines = []
        for paragraph in str(text).split("\n"):
            line = ""
            for char in paragraph:
                if line and self.draw.textlength(line + char, font=face) > width:
                    if char in NO_LINE_START and len(line) > 1:
                        lines.append(line[:-1])
                        line = line[-1]
                    else:
                        lines.append(line)
                        line = ""
                line += char
            lines.append(line)
        return lines

    def glow(self, center: tuple, radius: float, alpha: int):
        layer = Image.new("RGBA", self.image.size, (*YELLOW, 0))
        mask = Image.new("L", self.image.size, 0)
        x, y = center
        ImageDraw.Draw(mask).ellipse((x - radius, y - radius, x + radius, y + radius), fill=alpha)
        layer.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * 0.45)))
        self.image.alpha_composite(layer)
        self.refresh()

    def shadow(self, box: tuple, radius: int, blur: int, alpha: int, offset: int = 0):
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        x0, y0, x1, y1 = box
        ImageDraw.Draw(layer).rounded_rectangle(
            (x0, y0 + offset, x1, y1 + offset), radius=radius, fill=(0, 0, 0, alpha)
        )
        self.image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
        self.refresh()

    def paste(self, art: Image.Image, xy: tuple, radius: int):
        mask = Image.new("L", art.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *art.size), radius=radius, fill=255)
        self.image.paste(art, xy, mask)
        self.refresh()

    def progress(self, x0: int, x1: int, y: int, ratio: float, height: int = 14):
        """奶黄到眼睛绿的渐变进度条。"""
        self.draw.rounded_rectangle((x0, y, x1, y + height), radius=height // 2, fill=SURFACE1)
        if ratio <= 0:
            return
        width = max(height, int((x1 - x0) * min(ratio, 1)))
        shade = Image.linear_gradient("L").rotate(90, expand=True).resize((width, height))
        bar = Image.composite(
            Image.new("RGB", shade.size, YELLOW), Image.new("RGB", shade.size, GREEN), shade
        )
        self.paste(bar, (x0, y), height // 2)

    def header(self, title: str, right: str, size: int = 72):
        self.text(title, (PAD - 4, 60), size, YELLOW_L, 800)
        width = self.image.width // 2 - PAD
        self.text(right, (self.image.width - PAD, 122), 26, OVERLAY2, 500, "rs", width=width)


def load_art(root: Path, asset: str) -> Image.Image:
    with Image.open(root / "assets" / asset) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def thumbnail(root: Path, asset: str, size: tuple[int, int]) -> Image.Image:
    """居中裁切的缩略图，只在内存中生成，不写入磁盘。"""
    with Image.open(root / "assets" / asset) as source:
        # JPEG 可直接按比例缩小解码，省去整张大图的解码开销。
        source.draft("RGB", (size[0] * 2, size[1] * 2))
        art = ImageOps.exif_transpose(source).convert("RGB")
    fitted = ImageOps.fit(art, size, Image.Resampling.LANCZOS)
    art.close()
    return fitted


def clean_cards(root: Path):
    """仅清理一周未使用、且可以重新生成的界面图片。"""
    threshold = time.time() - 7 * 86400
    for directory, suffix in (("cards", "*.png"), ("cards", "*.tmp"), ("thumbnails", "*.png")):
        for path in (root / directory).glob(suffix):
            try:
                if path.stat().st_mtime < threshold:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
