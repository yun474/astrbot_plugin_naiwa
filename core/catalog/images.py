"""图片校验与按字节指纹归档。"""

import hashlib
import io
from pathlib import Path

from PIL import Image

from ..config import NaiwaError

MAX_BYTES = 10 * 1024 * 1024
FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def archive_image(path: Path, archive: Path, item_id: str) -> tuple[str, int, int]:
    """校验图片并存入归档目录，返回归档文件名与宽高。"""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Image too large")
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Image too large")
        suffix = path.suffix.lower()
        with Image.open(io.BytesIO(raw)) as img:
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"} or img.format not in FORMATS:
                raise ValueError("Unsupported image format")
            # 后缀与真实格式不一致时，归档素材按真实格式命名，保证上传 MIME 类型正确。
            suffix = FORMATS[img.format]
            if img.width * img.height > 16_000_000:
                raise ValueError("Image dimensions too large")
            width, height = img.size
            img.verify()
        # verify() 不会解码 JPEG 像素，这里直接校验实际归档的字节。
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
        asset = f"{hashlib.sha256(raw).hexdigest()}{suffix}"
        store(archive / asset, raw)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise NaiwaError(f"{item_id} 图片无法解析或超过限制。") from exc
    return asset, width, height


def store(dest: Path, raw: bytes):
    if not dest.exists():
        temp = dest.with_suffix(dest.suffix + ".tmp")
        temp.write_bytes(raw)
        temp.replace(dest)


def archived_size(archive: Path, asset: str) -> tuple[int, int] | None:
    """读取已归档图片的宽高；文件不存在或无法识别时返回 None。"""
    try:
        with Image.open(archive / asset) as img:
            return img.size
    except (OSError, ValueError):
        return None
