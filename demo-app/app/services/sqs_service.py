"""SQS service for queue messaging."""

from botocore.exceptions import ClientError

from ..config.settings import Settings
from ..utils.aws import make_client


class SQSService:
    def __init__(self, session, settings: Settings) -> None:
        self.settings = settings
        self.client = make_client(session, "sqs", settings)
        self._queue_url: str | None = None

    def queue_url(self) -> str:
        """Resolve the queue URL — GetQueueUrl first, idempotent CreateQueue fallback."""
        if self._queue_url is None:
            self._queue_url = self._resolve_queue_url()
        return self._queue_url

    def _resolve_queue_url(self) -> str:
        try:
            resp = self.client.get_queue_url(QueueName=self.settings.sqs_queue)
            return resp["QueueUrl"]
        except ClientError:
            pass
        resp = self.client.create_queue(QueueName=self.settings.sqs_queue)  # idempotent
        return resp["QueueUrl"]

    def send_message(self, body: str) -> str:
        resp = self.client.send_message(QueueUrl=self.queue_url(), MessageBody=body)
        return resp["MessageId"]

    def receive_and_delete(self, max_messages: int = 10) -> list[dict]:
        resp = self.client.receive_message(
            QueueUrl=self.queue_url(),
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=2,
        )
        messages = resp.get("Messages", [])
        out = [{"message_id": m["MessageId"], "body": m["Body"]} for m in messages]
        if messages:
            self.client.delete_message_batch(
                QueueUrl=self.queue_url(),
                Entries=[
                    {"Id": m["MessageId"], "ReceiptHandle": m["ReceiptHandle"]} for m in messages
                ],
            )
        return out
