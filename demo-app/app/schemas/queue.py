"""SQS queue request/response schemas."""

from pydantic import BaseModel, Field


class QueueSendRequest(BaseModel):
    body: str = Field(min_length=1)


class QueueSendResponse(BaseModel):
    message_id: str
    queue_url: str


class QueueMessageOut(BaseModel):
    message_id: str
    body: str


class QueueMessagesResponse(BaseModel):
    messages: list[QueueMessageOut]
    received: int
