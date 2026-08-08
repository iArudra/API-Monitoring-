"""Order request/response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class OrderItemIn(BaseModel):
    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(default=0.0, ge=0)


class OrderCreate(BaseModel):
    user_id: str = Field(min_length=1)
    items: list[OrderItemIn] = Field(min_length=1)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    user_id: str
    items: list[dict]
    total: float
    status: str
    created_at: str


class OrderListOut(BaseModel):
    orders: list[OrderOut]
    count: int
