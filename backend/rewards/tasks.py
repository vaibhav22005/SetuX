import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from firebase_admin.exceptions import FirebaseError
from firebase_admin import messaging

from donors.models import DonorDevice

from .firebase import send_push_message
from .models import DonorAlert

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(FirebaseError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def dispatch_pending_firebase_alerts(self, batch_size=100):
    if not settings.FIREBASE_ENABLED:
        logger.info("Skipping FCM delivery because FIREBASE_ENABLED is not set.")
        return 0

    delivery_cutoff = timezone.now() - timedelta(days=7)
    DonorAlert.objects.filter(
        push_pending=True,
        push_sent_at__isnull=True,
        created_at__lt=delivery_cutoff,
    ).update(push_pending=False)
    sent_count = 0
    alerts = DonorAlert.objects.filter(
        push_pending=True,
        push_sent_at__isnull=True,
        created_at__gte=delivery_cutoff,
    ).select_related("recipient").order_by("created_at")[:batch_size]
    for alert in alerts:
        devices = list(DonorDevice.objects.filter(user=alert.recipient))
        if not devices:
            continue

        for device in devices:
            try:
                send_push_message(
                    token=device.fcm_token,
                    title="SetuX donor alert",
                    body=alert.message,
                )
            except messaging.UnregisteredError:
                logger.info("Removing expired Firebase registration for user %s.", alert.recipient_id)
                device.delete()

        alert.push_pending = False
        alert.push_sent_at = timezone.now()
        alert.save(update_fields=("push_pending", "push_sent_at"))
        sent_count += 1
    return sent_count
