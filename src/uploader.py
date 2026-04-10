import boto3
from datetime import datetime, timezone


class S3Uploader:
    def __init__(self, bucket: str, prefix: str):
        self.bucket = bucket
        self.prefix = prefix
        self.client = boto3.client("s3")

    def _make_key(self, category: str, filename: str) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"{self.prefix}/{category}/{date_str}/{filename}"

    def _put(self, data: bytes, key: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="image/jpeg",
        )
        return key

    def upload_static(self, data: bytes, category: str, timestamp: str) -> str:
        key = self._make_key(category, f"{timestamp}_static.jpg")
        return self._put(data, key)

    def upload_frame(self, data: bytes, category: str, timestamp: str, frame_num: int) -> str:
        key = self._make_key(category, f"{timestamp}_frame_{frame_num:03d}.jpg")
        return self._put(data, key)
