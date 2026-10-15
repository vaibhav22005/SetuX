from django.db import transaction
from django.utils import timezone

from .models import DonorAlert, DonationRecord, RewardClaim


@transaction.atomic
def verify_donation(*, donor_profile, hospital, verified_by, donation_date, notes="", reward=None):
    donation = DonationRecord.objects.create(
        donor=donor_profile,
        hospital=hospital,
        verified_by=verified_by,
        donation_date=donation_date,
        notes=notes,
    )
    donor_profile.last_donation_date = max(
        donor_profile.last_donation_date or donation_date,
        donation_date,
    )
    donor_profile.save(update_fields=("last_donation_date", "updated_at"))

    if reward is not None:
        claim = RewardClaim.objects.create(donation=donation, reward=reward)
        DonorAlert.objects.create(
            recipient=donor_profile.user,
            category=DonorAlert.Category.REWARD,
            message=f"Your donation was verified. You can claim: {reward.title}.",
            dedupe_key=f"reward-claim:{claim.pk}",
        )

    DonorAlert.objects.create(
        recipient=donor_profile.user,
        category=DonorAlert.Category.DONATION,
        message=f"Your donation at {hospital.name} on {donation_date:%d %b %Y} was verified.",
        dedupe_key=f"donation-verified:{donation.pk}",
    )
    return donation


@transaction.atomic
def claim_reward(*, claim, donor_user):
    locked_claim = RewardClaim.objects.select_for_update().select_related(
        "donation__donor__user",
        "reward",
    ).get(pk=claim.pk)
    if locked_claim.donation.donor.user_id != donor_user.pk:
        raise PermissionError("This reward claim does not belong to the current donor.")
    if locked_claim.claimed_at is None:
        locked_claim.claimed_at = timezone.now()
        locked_claim.save(update_fields=("claimed_at",))
        DonorAlert.objects.create(
            recipient=donor_user,
            category=DonorAlert.Category.REWARD,
            message=f"Your claim code for {locked_claim.reward.title} is {locked_claim.claim_code}.",
            dedupe_key=f"reward-claimed:{locked_claim.pk}",
        )
    return locked_claim
