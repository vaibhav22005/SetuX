from donors.services import donors_for_shortage
from rewards.models import DonorAlert

from .models import Hospital, ShortageRequest


def notify_shortage_donors(shortage):
    hospital = shortage.hospital
    location = f"{hospital.address[:180]}, {hospital.city[:80]}".strip(", ")
    alerts = [
        DonorAlert(
            recipient=donor.user,
            category=DonorAlert.Category.SHORTAGE,
            message=(
                f"{hospital.name[:150]} at {location} needs {shortage.units_needed} "
                f"{shortage.blood_group} blood unit(s). You are within "
                f"{shortage.radius_km} km of the center."
            )[:500],
            dedupe_key=f"shortage-request:{shortage.pk}",
            shortage_request=shortage,
        )
        for donor in donors_for_shortage(shortage)
    ]
    DonorAlert.objects.bulk_create(alerts, ignore_conflicts=True)
    return len(alerts)


def nearby_open_shortages_for_donor(donor_profile):
    if not donor_profile.is_available or donor_profile.latitude is None or donor_profile.longitude is None:
        return []

    candidates = ShortageRequest.objects.filter(
        status=ShortageRequest.Status.OPEN,
        blood_group=donor_profile.blood_group,
        hospital__is_active=True,
        hospital__approval_status=Hospital.ApprovalStatus.APPROVED,
    ).select_related("hospital")
    return [
        shortage
        for shortage in candidates
        if any(
            donor.pk == donor_profile.pk
            for donor in donors_for_shortage(shortage)
        )
    ]
