import io
from unittest.mock import Mock

from PIL import Image

from scripts import backfill_photo_dimensions as backfill


def test_dimensions_match_displayed_exif_orientation():
    file = io.BytesIO()
    with Image.new("RGB", (90, 60)) as image:
        exif = image.getexif()
        exif[274] = 6
        image.save(file, format="JPEG", exif=exif)
    file.seek(0)
    assert backfill.dimensions(file) == (60, 90)


def test_legacy_bucket_prefix_and_new_object_urls(monkeypatch):
    monkeypatch.setenv("s3_bucket_name", "portfolio-images")
    monkeypatch.setenv("s3_url", "https://portfolio.cdn.gadcoder.com/portfolio-images")
    assert backfill.object_key("https://portfolio.cdn.gadcoder.com/portfolio-images/folder/a%20b.jpg") == "folder/a b.jpg"
    assert backfill.object_key("https://portfolio.cdn.gadcoder.com/new.webp") == "new.webp"


def test_complete_file_fallback_and_streams_are_closed(monkeypatch):
    file = io.BytesIO()
    with Image.new("RGB", (80, 60)) as image:
        image.save(file, format="WEBP")
    partial = io.BytesIO(b"invalid partial header")
    full = Mock()
    full.iter_chunks.return_value = [file.getvalue()]
    storage = Mock()
    storage.get_object.side_effect = [{"Body": partial}, {"Body": full, "ContentLength": len(file.getvalue())}]
    monkeypatch.setattr(backfill, "s3_client", storage)
    monkeypatch.setenv("s3_bucket_name", "portfolio-images")
    assert backfill.stored_dimensions("https://portfolio.cdn.gadcoder.com/portfolio-images/image.webp") == (80, 60)
    assert partial.closed
    full.close.assert_called_once()
