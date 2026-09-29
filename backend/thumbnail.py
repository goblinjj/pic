import os
from PIL import Image, ImageOps

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
THUMB_DIR = os.path.join(UPLOAD_DIR, "thumbs")
THUMB_SIZE = (800, 800)
THUMB_QUALITY = 85
# 标记文件：存在即表示「按 EXIF 摆正」的缩略图重建已经做过
# 以后若再批量重建缩略图，记得同步加大前端 LogCard.vue 的 THUMB_VERSION，否则浏览器会继续显示缓存的旧图
ORIENTED_MARKER = ".oriented-v1"


def ensure_thumb_dir():
    os.makedirs(THUMB_DIR, exist_ok=True)


def generate_thumbnail(filename: str):
    """Generate a thumbnail for the given filename. Skips non-image files."""
    src = os.path.join(UPLOAD_DIR, filename)
    dst = os.path.join(THUMB_DIR, filename)
    ensure_thumb_dir()
    try:
        with Image.open(src) as img:
            # 手机竖拍的原图像素是横的、靠 EXIF 标记方向；存 JPEG 时 EXIF 会丢，
            # 所以必须先摆正，不然缩略图永远是横的
            img = ImageOps.exif_transpose(img)
            img.thumbnail(THUMB_SIZE)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(dst, "JPEG", quality=THUMB_QUALITY)
    except Exception:
        # Not an image or corrupt — skip silently
        pass


def delete_thumbnail(filename: str):
    """Delete the thumbnail for the given filename if it exists."""
    path = os.path.join(THUMB_DIR, filename)
    if os.path.exists(path):
        os.remove(path)


def _needs_rotation(path: str) -> bool:
    try:
        with Image.open(path) as img:
            return img.getexif().get(0x0112) not in (None, 1)
    except Exception:
        return False


def migrate_existing():
    """Generate thumbnails for all existing images that don't have one yet.

    旧版本生成缩略图时没按 EXIF 摆正：第一次启动新版本时，把带方向标记的原图
    的缩略图重建一遍，做完写标记文件，以后不再重复。
    """
    ensure_thumb_dir()
    if not os.path.isdir(UPLOAD_DIR):
        return
    marker = os.path.join(THUMB_DIR, ORIENTED_MARKER)
    reorient = not os.path.exists(marker)
    for fname in os.listdir(UPLOAD_DIR):
        src = os.path.join(UPLOAD_DIR, fname)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(THUMB_DIR, fname)
        if os.path.exists(dst) and not (reorient and _needs_rotation(src)):
            continue
        generate_thumbnail(fname)
    if reorient:
        with open(marker, "w"):
            pass
