"""User domain model (stored in DynamoDB)."""

from dataclasses import dataclass


@dataclass
class User:
    user_id: str
    email: str
    name: str
    created_at: str

    def to_item(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at,
        }

    @classmethod
    def from_item(cls, item: dict) -> "User":
        return cls(
            user_id=item["user_id"],
            email=item["email"],
            name=item.get("name", ""),
            created_at=item.get("created_at", ""),
        )
