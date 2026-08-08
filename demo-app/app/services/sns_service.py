"""SNS service for notifications (email/sms)."""

from botocore.exceptions import ClientError

from ..config.settings import Settings
from ..telemetry.logging import get_logger
from ..telemetry.metrics import BusinessMetrics
from ..telemetry.tracing import aws_attributes, business_span
from ..utils.aws import make_client

logger = get_logger(__name__)


class SNSService:
    def __init__(self, session, settings: Settings, metrics: BusinessMetrics) -> None:
        self.settings = settings
        self.client = make_client(session, "sns", settings)
        self._metrics = metrics
        self._topic_arn: str | None = None

    def topic_arn(self) -> str:
        """Resolve the topic ARN — ListTopics first, idempotent CreateTopic fallback.

        The fallback only runs when the topic cannot be found (LocalStack dev
        convenience); on real AWS the startup validation guarantees it exists.
        """
        if self._topic_arn is None:
            self._topic_arn = self._resolve_topic_arn()
        return self._topic_arn

    def _resolve_topic_arn(self) -> str:
        name = self.settings.sns_topic
        try:
            paginator = self.client.get_paginator("list_topics")
            for page in paginator.paginate():
                for topic in page.get("Topics", []):
                    if topic["TopicArn"].rsplit(":", 1)[-1] == name:
                        logger.info("Resolved SNS topic %s", topic["TopicArn"])
                        return topic["TopicArn"]
        except ClientError:
            pass
        resp = self.client.create_topic(Name=name)  # idempotent
        logger.info("Resolved SNS topic %s", resp["TopicArn"])
        return resp["TopicArn"]

    def publish(self, channel: str, recipient: str, subject: str, message: str) -> dict:
        """Publish a notification wrapped in a "Notification Workflow" business span."""
        with business_span(
            "Notification Workflow",
            attributes=aws_attributes(
                "sns",
                "Publish",
                {"topic.name": self.settings.sns_topic, "channel": channel, "endpoint": "/notifications"},
            ),
        ):
            resp = self.client.publish(
                TopicArn=self.topic_arn(),
                Subject=subject or f"Notification via {channel}",
                Message=message,
                MessageAttributes={
                    "channel": {"DataType": "String", "StringValue": channel},
                    "recipient": {"DataType": "String", "StringValue": recipient},
                },
            )
        self._metrics.notifications_sent.add(1, {"channel": channel, "status": "ok"})
        return {"message_id": resp["MessageId"], "channel": channel, "topic_arn": self.topic_arn()}
