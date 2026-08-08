"""Failure-simulation endpoints — exist ONLY to demonstrate observability."""

import asyncio
from uuid import uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends

from ..deps import get_container, require_auth
from ..services import Container

# Protected like every business router: these endpoints exist ONLY to exercise
# the observability pipeline, so they require a valid bearer token.
router = APIRouter(prefix="/simulate", tags=["simulate"], dependencies=[Depends(require_auth)])


class SimulatedFailure(Exception):
    """Deliberate 500 error for observability demos."""

    status_code = 500


class SimulatedAWSError(Exception):
    """Deliberate upstream AWS failure (502) for observability demos."""

    status_code = 502


@router.get("/error", summary="Return HTTP 500 (deliberate error)")
def simulate_error():
    raise SimulatedFailure("Simulated internal server error for observability demo")


@router.get("/timeout", summary="Sleep for several seconds (slow request)")
async def simulate_timeout(container: Container = Depends(get_container)):
    seconds = container.settings.simulate_timeout_seconds
    await asyncio.sleep(seconds)
    return {"status": "ok", "slept_for_seconds": seconds}


@router.get("/s3-error", summary="Attempt an S3 call against an invalid bucket")
def simulate_s3_error(container: Container = Depends(get_container)):
    bad_bucket = f"centralwatch-invalid-bucket-{uuid4().hex[:8]}"
    try:
        container.s3.client.put_object(Bucket=bad_bucket, Key="demo.txt", Body=b"demo")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise SimulatedAWSError(f"S3 put_object to invalid bucket '{bad_bucket}' failed: {code}") from exc
    raise SimulatedFailure("unreachable: S3 call unexpectedly succeeded")


@router.get("/retry", summary="Retry an AWS SDK call before succeeding (retry demo)")
def simulate_retry(container: Container = Depends(get_container)):
    return container.s3.list_buckets_with_retries()
