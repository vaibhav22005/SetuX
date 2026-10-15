from celery import shared_task
from django.utils import timezone

from donors.services import nearby_available_donors
from rewards.models import DonorAlert

from .models import Hospital, ShortageRequest
from .notifications import notify_shortage_donors
from .services import BLOOD_GROUPS, forecast_inventory_risk_for_group


@shared_task
def notify_open_shortages():
    notified_count = 0
    for shortage in ShortageRequest.objects.filter(
        status=ShortageRequest.Status.OPEN,
        hospital__is_active=True,
        hospital__approval_status=Hospital.ApprovalStatus.APPROVED,
    ).select_related("hospital").iterator():
        notified_count += notify_shortage_donors(shortage)
    return notified_count


@shared_task
def dispatch_inventory_risk_alerts():
    today = timezone.localdate()
    alerts = []
    hospitals = Hospital.objects.filter(
        is_active=True,
        approval_status=Hospital.ApprovalStatus.APPROVED,
    )
    for hospital in hospitals:
        for blood_group in BLOOD_GROUPS:
            risk = forecast_inventory_risk_for_group(hospital, blood_group)
            if risk["risk_level"] not in {"high", "watch"}:
                continue
            for donor in nearby_available_donors(hospital, blood_group, radius_km=10):
                alerts.append(
                    DonorAlert(
                        recipient=donor.user,
                        category=DonorAlert.Category.FORECAST,
                        message=(
                            f"{hospital.name} may have a {risk['risk_level']} "
                            f"{blood_group} inventory shortage. Current stock: "
                            f"{risk['current_units']} unit(s); safe threshold: "
                            f"{risk['safe_threshold']}."
                        ),
                        dedupe_key=(
                            f"inventory-risk:{hospital.pk}:{blood_group}:"
                            f"{today.isoformat()}:{risk['risk_level']}"
                        ),
                    )
                )
    DonorAlert.objects.bulk_create(alerts, ignore_conflicts=True)
    return len(alerts)
