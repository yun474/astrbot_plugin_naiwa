"""图片感知指纹：用于判断两张图是否为同一张图的不同编码。"""

from PIL import Image

# 两个指纹的汉明距离不超过该值时视为同一张图。
SAME_IMAGE_DISTANCE = 8


def dhash(image: Image.Image) -> str:
    """256 位差值哈希：透明区域先铺白底，再比较相邻灰度。"""
    rgba = image.convert("RGBA")
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat.alpha_composite(rgba)
    gray = flat.convert("L").resize((17, 16), Image.Resampling.LANCZOS)
    pixels = gray.load()
    bits = 0
    for y in range(16):
        for x in range(16):
            bits = bits << 1 | (pixels[x + 1, y] > pixels[x, y])
    return f"{bits:064x}"


def distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
