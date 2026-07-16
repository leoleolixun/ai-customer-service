from app.core.errors import AppError


class MemoryObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def check_ready(self) -> None:
        return None

    async def put(self, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = (content, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key][0]
        except KeyError as exc:
            raise AppError(
                status_code=503,
                code="object_storage_read_failed",
                title="Object storage unavailable",
                detail="The knowledge document could not be read from object storage.",
            ) from exc

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
