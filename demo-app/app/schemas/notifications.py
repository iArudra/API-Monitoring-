"""Notification request/response schemas."""

from pydantic import BaseModel, Field


class NotificationRequest(BaseModel):
    recipient: str = Field(min_length=1, examples=["alice@example.com"])
    subject: str = Field(default="", max_length=200)
    message: str = Field(min_length=1)


class NotificationResponse(BaseModel):
    message_id: str
    channel: str
    topic_arn: str
