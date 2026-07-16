from functools import lru_cache

from app.providers.storage.base import ObjectStorage
from app.providers.storage.s3 import S3ObjectStorage


@lru_cache
def get_object_storage() -> ObjectStorage:
    return S3ObjectStorage()
