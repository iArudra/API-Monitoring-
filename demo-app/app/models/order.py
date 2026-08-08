"""Order domain model (stored in DynamoDB)."""

from dataclasses import dataclass, field

from ..utils.ids import now_iso


@dataclass
class Order:
    order_id: str
    user_id: str
    items: list[dict]
    total: float
    status: str = "created"
    created_at: str = field(default_factory=now_iso)

    def to_item(self) -> dict:
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "items": self.items,
            "total": self.total,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_item(cls, item: dict) -> "Order":
        return cls(
            order_id=item["order_id"],
            user_id=item.get("user_id", ""),
            items=item.get("items", []),
            total=float(item.get("total", 0.0)),
            status=item.get("status", "created"),
            created_at=item.get("created_at", ""),
        )
