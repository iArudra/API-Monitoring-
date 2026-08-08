"""Notification routes (SNS via LocalStack)."""

from fastapi import APIRouter, Depends

from ..deps import get_container, require_auth
from ..schemas.notifications import NotificationRequest, NotificationResponse
from ..services import Container

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_auth)])


@router.post("/email", response_model=NotificationResponse, summary="Send an email notification (SNS)")
def send_email(body: NotificationRequest, container: Container = Depends(get_container)) -> NotificationResponse:
    return container.sns.publish(channel="email", recipient=body.recipient, subject=body.subject or "Email notification", message=body.message)


@router.post("/sms", response_model=NotificationResponse, summary="Send an SMS notification (SNS)")
def send_sms(body: NotificationRequest, container: Container = Depends(get_container)) -> NotificationResponse:
    return container.sns.publish(channel="sms", recipient=body.recipient, subject="SMS notification", message=body.message)
