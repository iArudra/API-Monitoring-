"""S3 service for object storage (against the emulated endpoint)."""

from botocore.exceptions import ClientError

from ..config.settings import Settings
from ..telemetry.metrics import BusinessMetrics
from ..utils.aws import make_client, retry_operation


class S3Service:
    def __init__(self, session, settings: Settings, metrics: BusinessMetrics) -> None:
        self.settings = settings
        self.client = make_client(session, "s3", settings)
        self.bucket = settings.s3_bucket
        self._metrics = metrics

    def upload(self, key: str, body: bytes, content_type: str | None = None, metadata: dict | None = None) -> str:
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        if metadata:
            extra["Metadata"] = metadata
        resp = self.client.put_object(Bucket=self.bucket, Key=key, Body=body, **extra)
        return resp["ETag"]

    def download(self, key: str) -> tuple[bytes, str]:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read(), resp.get("ContentType", "application/octet-stream")

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_url(self, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )

    def list_buckets(self) -> list[str]:
        return [b["Name"] for b in self.client.list_buckets().get("Buckets", [])]

    def list_buckets_with_retries(self) -> dict:
        """Fail twice with a simulated throttling error, then succeed (retry demo).

        Emits a "Retry Operation" span with per-attempt child spans.
        """
        state = {"failures_left": 2, "attempts": 0}

        def _record_retry(_attempt: int) -> None:
            self._metrics.retry_attempts.add(1, {"operation": "S3.ListBuckets"})

        @retry_operation(max_attempts=self.settings.simulate_retry_attempts, operation="S3.ListBuckets", on_retry=_record_retry)
        def _call() -> list[str]:
            state["attempts"] += 1
            if state["failures_left"] > 0:
                state["failures_left"] -= 1
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException", "Message": "Simulated rate limiting"}},
                    "ListBuckets",
                )
            return self.list_buckets()

        buckets = _call()
        return {"status": "ok", "attempts": state["attempts"], "buckets": buckets}
