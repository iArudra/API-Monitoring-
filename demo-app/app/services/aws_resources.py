"""AWS resource management: provisioning (LocalStack/dev) and validation (real AWS).

Two modes, controlled by ``aws_provision_resources``:

- ``true`` — idempotently create any missing resources at startup and on a
  periodic reconcile loop (intended for LocalStack / development). Safe to call
  repeatedly; existing resources are detected and left untouched.
- ``false`` (default; real AWS) — validate that every required resource already
  exists and fail fast with a clear error message if any are missing.
"""

import io
import time
import urllib.request
import zipfile

from botocore.exceptions import ClientError

from ..config.settings import Settings
from ..telemetry.logging import get_logger

logger = get_logger(__name__)

LAMBDA_HANDLER_CODE = r'''
import json
import os
import time
import uuid

import boto3
from botocore.config import Config

_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _client(name):
    """Client using the default credential chain.

    An endpoint (LocalStack) is only used when AWS_ENDPOINT_URL is set; on real
    AWS the SDK talks to the regional default endpoints using the Lambda
    execution role's credentials.
    """
    kwargs = {"region_name": _REGION}
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        if name == "s3":
            kwargs["config"] = Config(s3={"addressing_style": "path"})
    return boto3.client(name, **kwargs)


def lambda_handler(event, context):
    bucket = event.get("bucket")
    key = event.get("key")
    topic = event.get("topic_arn")
    traceparent = event.get("traceparent")

    if event.get("warmup"):
        return {"statusCode": 200, "body": json.dumps({"status": "warm"})}

    # 1. Read the uploaded image from S3.
    s3 = _client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    size = len(body)

    # 2. Simulate CPU-bound image processing.
    time.sleep(0.5)

    processing_id = str(uuid.uuid4())
    result = {
        "status": "processed",
        "processing_id": processing_id,
        "bucket": bucket,
        "key": key,
        "size_bytes": size,
        "traceparent": traceparent,
    }

    # 3. Notify via SNS.
    if topic:
        sns = _client("sns")
        sns.publish(
            TopicArn=topic,
            Subject="Image processed",
            Message=json.dumps(result),
            MessageAttributes={
                "channel": {"DataType": "String", "StringValue": "image-processor"},
                "processing_id": {"DataType": "String", "StringValue": processing_id},
            },
        )
        result["notification"] = "published"

    return {"statusCode": 200, "body": json.dumps(result)}
'''


def _describe(exc: Exception) -> str:
    """Short human-readable description of a botocore error."""
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        return f"{error.get('Code', 'ClientError')}: {error.get('Message', str(exc))}"
    return f"{type(exc).__name__}: {exc}"


class AwsResourceManager:
    """Creates (provision mode) or validates (validate mode) AWS resources."""

    def __init__(self, settings: Settings, session) -> None:
        self.settings = settings
        self.session = session

    # -------------------------------------------------------------- mode helpers
    @property
    def is_localstack(self) -> bool:
        """True when an explicit endpoint is configured (LocalStack / custom)."""
        return bool(self.settings.aws_endpoint_url)

    # --------------------------------------------------------------- readiness
    def _health_url(self) -> str:
        return f"{self.settings.aws_endpoint_url.rstrip('/')}/_localstack/health"

    def is_ready(self) -> bool:
        try:
            with urllib.request.urlopen(self._health_url(), timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def wait_until_ready(self, timeout: float = 120.0, poll: float = 3.0) -> bool:
        """Wait for LocalStack readiness. Skipped when no endpoint is configured."""
        if not self.is_localstack:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_ready():
                return True
            time.sleep(poll)
        return False

    # -------------------------------------------------------------- provisioning
    def ensure_resources(self, log_summary: bool = True) -> None:
        """Create any missing resources (provision mode). Idempotent."""
        self._ensure_s3_bucket()
        self._ensure_dynamodb_tables()
        self._ensure_sns_topic()
        self._ensure_sqs_queue()
        self._ensure_lambda_function()
        if log_summary:
            logger.info("AWS resources ensured (bucket, tables, topic, queue, lambda)")

    def _client(self, service):
        from ..utils.aws import make_client

        return make_client(self.session, service, self.settings)

    def _ensure_s3_bucket(self) -> None:
        client = self._client("s3")
        bucket = self.settings.s3_bucket
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchBucket", "403"):
                logger.warning("Unexpected head_bucket response for %s: %s", bucket, code)
            kwargs = {}
            if self.settings.aws_region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.settings.aws_region}
            client.create_bucket(Bucket=bucket, **kwargs)
            logger.info("Created S3 bucket %s", bucket)

    def _table_definitions(self) -> list[dict]:
        s = self.settings
        return [
            {
                "TableName": s.dynamodb_users_table,
                "AttributeDefinitions": [
                    {"AttributeName": "user_id", "AttributeType": "S"},
                    {"AttributeName": "email", "AttributeType": "S"},
                ],
                "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "email-index",
                        "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ],
                "BillingMode": "PAY_PER_REQUEST",
            },
            {
                "TableName": s.dynamodb_orders_table,
                "AttributeDefinitions": [{"AttributeName": "order_id", "AttributeType": "S"}],
                "KeySchema": [{"AttributeName": "order_id", "KeyType": "HASH"}],
                "BillingMode": "PAY_PER_REQUEST",
            },
            {
                "TableName": s.dynamodb_files_table,
                "AttributeDefinitions": [{"AttributeName": "file_id", "AttributeType": "S"}],
                "KeySchema": [{"AttributeName": "file_id", "KeyType": "HASH"}],
                "BillingMode": "PAY_PER_REQUEST",
            },
        ]

    def _ensure_dynamodb_tables(self) -> None:
        client = self._client("dynamodb")
        for definition in self._table_definitions():
            try:
                client.describe_table(TableName=definition["TableName"])
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                    raise
                client.create_table(**definition)
                logger.info("Created DynamoDB table %s", definition["TableName"])

    def _ensure_sns_topic(self) -> None:
        client = self._client("sns")
        resp = client.create_topic(Name=self.settings.sns_topic)  # idempotent
        logger.debug("SNS topic %s ready: %s", self.settings.sns_topic, resp.get("TopicArn"))

    def _ensure_sqs_queue(self) -> None:
        client = self._client("sqs")
        resp = client.create_queue(QueueName=self.settings.sqs_queue)  # idempotent
        logger.debug("SQS queue %s ready: %s", self.settings.sqs_queue, resp.get("QueueUrl"))

    def _ensure_lambda_function(self) -> None:
        client = self._client("lambda")
        name = self.settings.lambda_function
        try:
            client.get_function(FunctionName=name)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                raise
            if not self.settings.lambda_role_arn:
                raise RuntimeError(
                    "LAMBDA_ROLE_ARN is not set; it is required to create the Lambda function "
                    "(LocalStack accepts any ARN, e.g. "
                    "arn:aws:iam::000000000000:role/centralwatch-lambda-role)"
                )
            env_vars = {"AWS_REGION": self.settings.aws_region}
            if self.is_localstack:
                env_vars["AWS_ENDPOINT_URL"] = self.settings.aws_endpoint_url
                if self.settings.aws_access_key_id:
                    env_vars["AWS_ACCESS_KEY_ID"] = self.settings.aws_access_key_id
                    env_vars["AWS_SECRET_ACCESS_KEY"] = self.settings.aws_secret_access_key
            client.create_function(
                FunctionName=name,
                Runtime="python3.11",
                Role=self.settings.lambda_role_arn,
                Handler="handler.lambda_handler",
                Code={"ZipFile": self._lambda_zip()},
                Timeout=30,
                MemorySize=256,
                Architectures=["x86_64"],
                Environment={"Variables": env_vars},
            )
            logger.info("Created Lambda function %s", name)

    @staticmethod
    def _lambda_zip() -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("handler.py", LAMBDA_HANDLER_CODE)
        return buffer.getvalue()

    # ----------------------------------------------------------------- validation
    def validate_resources(self) -> None:
        """Fail fast when any required resource is missing or unreachable (real AWS)."""
        missing: list[str] = []

        s3 = self._client("s3")
        try:
            s3.head_bucket(Bucket=self.settings.s3_bucket)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"S3 bucket '{self.settings.s3_bucket}': {_describe(exc)}")

        dynamodb = self._client("dynamodb")
        for definition in self._table_definitions():
            name = definition["TableName"]
            try:
                table = dynamodb.describe_table(TableName=name)["Table"]
            except Exception as exc:  # noqa: BLE001
                missing.append(f"DynamoDB table '{name}': {_describe(exc)}")
                continue

            # Verify every GSI the application relies on (e.g. the users table's
            # email-index) exists with the expected key schema. This is checked
            # only in validate mode (real AWS) — provisioning never changes.
            indexes = {idx["IndexName"]: idx for idx in table.get("GlobalSecondaryIndexes", [])}
            for gsi in definition.get("GlobalSecondaryIndexes", []):
                index_name = gsi["IndexName"]
                if index_name not in indexes:
                    missing.append(
                        f"DynamoDB table '{name}' is missing GSI '{index_name}' "
                        f"(required by the application: {index_name})"
                    )
                    continue
                actual_schema = indexes[index_name].get("KeySchema")
                if actual_schema != gsi["KeySchema"]:
                    missing.append(
                        f"DynamoDB table '{name}' GSI '{index_name}' has unexpected key schema "
                        f"{actual_schema}; expected {gsi['KeySchema']}"
                    )

        sns = self._client("sns")
        try:
            found = False
            paginator = sns.get_paginator("list_topics")
            for page in paginator.paginate():
                if any(
                    t["TopicArn"].rsplit(":", 1)[-1] == self.settings.sns_topic for t in page.get("Topics", [])
                ):
                    found = True
                    break
            if not found:
                missing.append(f"SNS topic '{self.settings.sns_topic}': not found (ListTopics)")
        except Exception as exc:  # noqa: BLE001
            missing.append(f"SNS topic '{self.settings.sns_topic}': {_describe(exc)}")

        sqs = self._client("sqs")
        try:
            sqs.get_queue_url(QueueName=self.settings.sqs_queue)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"SQS queue '{self.settings.sqs_queue}': {_describe(exc)}")

        lam = self._client("lambda")
        try:
            lam.get_function(FunctionName=self.settings.lambda_function)
        except Exception as exc:  # noqa: BLE001
            missing.append(f"Lambda function '{self.settings.lambda_function}': {_describe(exc)}")

        if missing:
            raise RuntimeError(
                "AWS resource validation failed (aws_provision_resources=false, so nothing "
                "was created). Missing or unreachable resources:\n  - "
                + "\n  - ".join(missing)
            )
        logger.info("AWS resource validation passed (bucket, tables, topic, queue, lambda)")
