"""Queue routes (SQS via LocalStack)."""

from fastapi import APIRouter, Depends

from ..deps import get_container, require_auth
from ..schemas.queue import QueueMessagesResponse, QueueSendRequest, QueueSendResponse
from ..services import Container

router = APIRouter(prefix="/queue", tags=["queue"], dependencies=[Depends(require_auth)])


@router.post("/send", response_model=QueueSendResponse, summary="Send a message to the queue (SQS)")
def send_message(body: QueueSendRequest, container: Container = Depends(get_container)) -> QueueSendResponse:
    message_id = container.sqs.send_message(body.body)
    return QueueSendResponse(message_id=message_id, queue_url=container.sqs.queue_url())


@router.get("/messages", response_model=QueueMessagesResponse, summary="Receive (and delete) messages from the queue (SQS)")
def receive_messages(container: Container = Depends(get_container)) -> QueueMessagesResponse:
    messages = container.sqs.receive_and_delete(max_messages=10)
    return QueueMessagesResponse(messages=messages, received=len(messages))
