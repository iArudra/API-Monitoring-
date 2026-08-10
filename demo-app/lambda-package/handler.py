
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
