import io
import os

from PIL import Image

import thumbnail


def _sideways_phone_jpeg(path, size=(1600, 1200)):
    """手机竖拍的存法：像素是横的，EXIF 标记「顺时针转 90°」。"""
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", size, (200, 30, 30)).save(path, "JPEG", exif=exif.tobytes())


def test_thumbnail_is_rotated_upright(client):
    os.makedirs(thumbnail.UPLOAD_DIR, exist_ok=True)
    _sideways_phone_jpeg(os.path.join(thumbnail.UPLOAD_DIR, "portrait.jpg"))
    thumbnail.generate_thumbnail("portrait.jpg")
    with Image.open(os.path.join(thumbnail.THUMB_DIR, "portrait.jpg")) as t:
        assert t.size == (600, 800)


def test_migrate_regenerates_stale_sideways_thumbnails_once(client):
    os.makedirs(thumbnail.THUMB_DIR, exist_ok=True)
    marker = os.path.join(thumbnail.THUMB_DIR, thumbnail.ORIENTED_MARKER)
    if os.path.exists(marker):
        os.remove(marker)
    _sideways_phone_jpeg(os.path.join(thumbnail.UPLOAD_DIR, "old.jpg"))
    # 旧版本生成的缩略图：没摆正、也没有 EXIF
    Image.new("RGB", (800, 600)).save(os.path.join(thumbnail.THUMB_DIR, "old.jpg"), "JPEG")

    thumbnail.migrate_existing()
    with Image.open(os.path.join(thumbnail.THUMB_DIR, "old.jpg")) as t:
        assert t.size == (600, 800)
    assert os.path.exists(marker)

    # 已迁移过：再跑一次不会重新生成（这里故意放回横的，验证不被改动）
    Image.new("RGB", (800, 600)).save(os.path.join(thumbnail.THUMB_DIR, "old.jpg"), "JPEG")
    thumbnail.migrate_existing()
    with Image.open(os.path.join(thumbnail.THUMB_DIR, "old.jpg")) as t:
        assert t.size == (800, 600)
