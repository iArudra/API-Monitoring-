"""File metadata domain model (object lives in S3, metadata in DynamoDB)."""

from dataclasses import dataclass, field

from ..utils.ids import now_iso


@dataclass
class FileRecord:
    file_id: str
    name: str
    size: int
    content_type: str
    bucket: str
    key: str
    created_at: str = field(default_factory=now_iso)

    def to_item(self) -> dict:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "size": self.size,
            "content_type": self.content_type,
            "bucket": self.bucket,
            "key": self.key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_item(cls, item: dict) -> "FileRecord":
        return cls(
            file_id=item["file_id"],
            name=item.get("name", ""),
            size=int(item.get("size", 0)),
            content_type=item.get("content_type", "application/octet-stream"),
            bucket=item.get("bucket", ""),
            key=item.get("key", ""),
            created_at=item.get("created_at", ""),
        )
