"""Lambda service orchestrating the image processing workflow (S3 -> Lambda -> SNS)."""

import json
from uuid import uuid4

from ..config.settings import Settings
from ..telemetry.logging import get_logger
from ..telemetry.metrics import BusinessMetrics
from ..telemetry.tracing import aws_attributes, business_span, current_traceparent
from ..utils.aws import make_client

logger = get_logger(__name__)


class LambdaService:
    def __init__(self, session, settings: Settings, s3_service, sns_service, metrics: BusinessMetrics) -> None:
        self.settings = settings
        # Lambda sidecar first run may need to pull the runtime image.
        self.client = make_client(session, "lambda", settings, read_timeout=300)
        self.s3 = s3_service
        self.sns = sns_service
        self._metrics = metrics

    def process_image(self, filename: str, content: bytes, content_type: str | None) -> dict:
        """Run the full business workflow under one parent span:
        Upload image -> S3, invoke -> Lambda, notify -> SNS, return response.
        """
        key = f"images/{uuid4().hex}.{self._extension(filename)}"
        attributes = aws_attributes(
            "lambda",
            "Invoke",
            {"bucket.name": self.settings.s3_bucket, "endpoint": "/images/process"},
        )
        with business_span("Image Processing Workflow", attributes=attributes):
            self.s3.upload(
                key,
                content,
                content_type=content_type,
                metadata={"original_filename": filename or "image.bin"},
            )

            payload = {
                "bucket": self.settings.s3_bucket,
                "key": key,
                "topic_arn": self.sns.topic_arn(),
                "traceparent": current_traceparent(),
            }
            resp = self.client.invoke(
                FunctionName=self.settings.lambda_function,
                Payload=json.dumps(payload),
            )
            body = self._parse_invoke(resp)

        self._metrics.images_processed.add(1, {"status": "ok"})
        return body

    def warm_up(self) -> None:
        """Invoke the processor once so the Lambda runtime image is pulled (first call is slow)."""
        resp = self.client.invoke(
            FunctionName=self.settings.lambda_function,
            Payload=json.dumps({"warmup": True}),
        )
        resp["Payload"].read()
        logger.info("Lambda warm-up complete (status_code=%s)", resp.get("StatusCode"))

    @staticmethod
    def _parse_invoke(resp) -> dict:
        raw = resp["Payload"].read().decode("utf-8")
        data = json.loads(raw)
        if resp.get("FunctionError") or data.get("statusCode", 200) != 200:
            raise RuntimeError(f"Lambda processing failed: {data}")
        return json.loads(data.get("body", "{}"))

    @staticmethod
    def _extension(filename: str | None) -> str:
        if filename and "." in filename:
            return filename.rsplit(".", 1)[-1].lower()[:8]
        return "bin"
