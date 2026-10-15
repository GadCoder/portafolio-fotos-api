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


def missing_key():
    from botocore.exceptions import ClientError
    return ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")


def test_full_path_can_be_the_actual_key(monkeypatch):
    monkeypatch.setenv("s3_bucket_name", "portfolio-images")
    monkeypatch.setenv("s3_url", "https://portfolio.cdn.gadcoder.com/portfolio-images")
    read = Mock(side_effect=[missing_key(), (80, 60)])
    public = Mock()
    monkeypatch.setattr(backfill, "r2_dimensions", read)
    monkeypatch.setattr(backfill, "public_dimensions", public)
    assert backfill.stored_dimensions("https://portfolio.cdn.gadcoder.com/portfolio-images/a.jpg") == (80, 60)
    assert [call.args[0] for call in read.call_args_list] == ["a.jpg", "portfolio-images/a.jpg"]
    public.assert_not_called()


def test_missing_r2_keys_fall_back_to_exact_public_original(monkeypatch):
    monkeypatch.setenv("s3_bucket_name", "portfolio-images")
    monkeypatch.setenv("s3_url", "https://portfolio.cdn.gadcoder.com/portfolio-images")
    monkeypatch.setattr(backfill, "r2_dimensions", Mock(side_effect=missing_key()))
    public = Mock(return_value=(90, 60))
    monkeypatch.setattr(backfill, "public_dimensions", public)
    url = "https://portfolio.cdn.gadcoder.com/portfolio-images/a.jpg"
    assert backfill.stored_dimensions(url) == (90, 60)
    public.assert_called_once_with(url)


def test_storage_permission_errors_are_not_hidden(monkeypatch):
    import pytest
    from botocore.exceptions import ClientError
    monkeypatch.setenv("s3_bucket_name", "portfolio-images")
    error = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
    monkeypatch.setattr(backfill, "r2_dimensions", Mock(side_effect=error))
    public = Mock()
    monkeypatch.setattr(backfill, "public_dimensions", public)
    with pytest.raises(ClientError):
        backfill.stored_dimensions("https://portfolio.cdn.gadcoder.com/portfolio-images/a.jpg")
    public.assert_not_called()


def test_public_original_preserves_url_orientation_and_closes_response(monkeypatch):
    file = io.BytesIO()
    with Image.new("RGB", (90, 60)) as image:
        exif = image.getexif()
        exif[274] = 6
        image.save(file, format="JPEG", exif=exif)
    response = io.BytesIO(file.getvalue())
    response.headers = {"Content-Length": str(len(file.getvalue()))}
    open_url = Mock(return_value=response)
    monkeypatch.setattr(backfill, "urlopen", open_url)
    url = "https://portfolio.cdn.gadcoder.com/portfolio-images/a.jpg"
    assert backfill.public_dimensions(url) == (60, 90)
    open_url.assert_called_once()
    request = open_url.call_args.args[0]
    assert request.full_url == url
    assert request.get_header("User-agent") == "PortfolioPhotoMetadata/1.0"
    assert open_url.call_args.kwargs["timeout"] == 30
    assert response.closed


def test_public_fallback_rejects_unknown_hosts_and_oversized_downloads(monkeypatch):
    import pytest
    monkeypatch.setenv("s3_url", "https://portfolio.cdn.gadcoder.com")
    open_url = Mock()
    monkeypatch.setattr(backfill, "urlopen", open_url)
    with pytest.raises(ValueError, match="configured HTTPS image host"):
        backfill.public_dimensions("http://internal.example/image.jpg")
    open_url.assert_not_called()
    response = io.BytesIO(b"x" * 20)
    response.headers = {}
    monkeypatch.setattr(backfill, "MAX_BYTES", 10)
    open_url.return_value = response
    with pytest.raises(ValueError, match="exceeds 50 MB"):
        backfill.public_dimensions("https://portfolio.cdn.gadcoder.com/image.jpg")
    assert response.closed
