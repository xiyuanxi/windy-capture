import pytest
from unittest.mock import MagicMock, patch
from src.uploader import S3Uploader


@pytest.fixture
def uploader():
    with patch("src.uploader.boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        u = S3Uploader(bucket="test-bucket", prefix="windy-capture")
        u._mock_client = mock_client
        yield u


def test_upload_static_puts_object(uploader):
    uploader.upload_static(b"fake-image-data", category="radar", timestamp="14-00-00")
    uploader._mock_client.put_object.assert_called_once()
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Body"] == b"fake-image-data"
    assert call_kwargs["ContentType"] == "image/jpeg"


def test_upload_static_key_contains_category_and_timestamp(uploader):
    uploader.upload_static(b"data", category="radar", timestamp="14-00-00")
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "windy-capture" in key
    assert "radar" in key
    assert "14-00-00_static.jpg" in key


def test_upload_frame_key_format(uploader):
    uploader.upload_frame(b"data", category="satellite", timestamp="09-30-00", frame_num=3)
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "satellite" in key
    assert "09-30-00_frame_003.jpg" in key


def test_upload_frame_zero_padded(uploader):
    uploader.upload_frame(b"data", category="wind", timestamp="00-05-00", frame_num=1)
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "00-05-00_frame_001.jpg" in key


def test_s3_key_includes_date_folder(uploader):
    with patch("src.uploader.datetime") as mock_dt:
        from datetime import datetime, timezone
        mock_dt.now.return_value = datetime(2026, 4, 10, 14, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.side_effect = lambda tz=None: datetime(2026, 4, 10, 14, 0, 0, tzinfo=timezone.utc)
        uploader.upload_static(b"data", category="radar", timestamp="14-00-00")
    call_kwargs = uploader._mock_client.put_object.call_args[1]
    key = call_kwargs["Key"]
    assert "2026-04-10" in key
