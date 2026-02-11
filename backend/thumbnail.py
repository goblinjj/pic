import os
from PIL import Image

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
THUMB_DIR = os.path.join(UPLOAD_DIR, "thumbs")
THUMB_SIZE = (800, 800)
THUMB_QUALITY = 85


def ensure_thumb_dir():
    os.makedirs(THUMB_DIR, exist_ok=True)


def generate_thumbnail(filename: str):
    """Generate a thumbnail for the given filename. Skips non-image files."""
    src = os.path.join(UPLOAD_DIR, filename)
    dst = os.path.join(THUMB_DIR, filename)
    ensure_thumb_dir()
    try:
        with Image.open(src) as img:
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


def migrate_existing():
    """Generate thumbnails for all existing images that don't have one yet."""
    ensure_thumb_dir()
    if not os.path.isdir(UPLOAD_DIR):
        return
    for fname in os.listdir(UPLOAD_DIR):
        src = os.path.join(UPLOAD_DIR, fname)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(THUMB_DIR, fname)
        if os.path.exists(dst):
            continue
        generate_thumbnail(fname)
