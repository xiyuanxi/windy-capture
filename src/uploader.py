import boto3
from datetime import datetime, timezone


class S3Uploader:
    def __init__(self, bucket: str, prefix: str):
        self.bucket = bucket
        self.prefix = prefix
        self.client = boto3.client("s3")

    def _make_key(self, category: str, date_str: str, filename: str) -> str:
        return f"{self.prefix}/{category}/{date_str}/{filename}"

    def _put(self, data: bytes, key: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="image/jpeg",
        )
        return key

    def upload_static(self, data: bytes, category: str, timestamp: str, date_str: str = "") -> str:
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = self._make_key(category, date_str, f"{timestamp}_static.jpg")
        return self._put(data, key)

    def upload_frame(self, data: bytes, category: str, timestamp: str, frame_num: int, date_str: str = "") -> str:
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = self._make_key(category, date_str, f"{timestamp}_frame_{frame_num:03d}.jpg")
        return self._put(data, key)
