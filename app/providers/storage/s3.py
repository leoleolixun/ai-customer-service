import asyncio
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.errors import AppError


class S3ObjectStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
        )

    async def check_ready(self) -> None:
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        await self.ensure_bucket()
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        try:
            response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
            return await asyncio.to_thread(response["Body"].read)
        except ClientError as exc:
            raise AppError(
                status_code=503,
                code="object_storage_read_failed",
                title="Object storage unavailable",
                detail="The knowledge document could not be read from object storage.",
            ) from exc

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    def _ensure_bucket_sync(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
