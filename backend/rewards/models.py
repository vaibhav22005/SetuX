import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Reward(models.Model):
    class RewardType(models.TextChoices):
        HEALTH_CHECKUP = "health_checkup", "Health checkup"
        DOCTOR_CONSULTATION = "doctor_consultation", "Doctor consultation"
        PARTNER_PERK = "partner_perk", "Partner perk"

    title = models.CharField(max_length=150)
    description = models.TextField()
    reward_type = models.CharField(max_length=30, choices=RewardType.choices)
    provider_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class DonationRecord(models.Model):
    donor = models.ForeignKey(
        "donors.DonorProfile",
        on_delete=models.PROTECT,
        related_name="donation_records",
    )
    hospital = models.ForeignKey(
        "inventory.Hospital",
        on_delete=models.PROTECT,
        related_name="verified_donations",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verified_donations",
    )
    donation_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-donation_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("donor", "donation_date"),
                name="unique_donor_donation_per_day",
            ),
        ]

    def __str__(self):
        return f"{self.donor} - {self.donation_date}"


class RewardClaim(models.Model):
    donation = models.OneToOneField(
        DonationRecord,
        on_delete=models.PROTECT,
        related_name="reward_claim",
    )
    reward = models.ForeignKey(
        Reward,
        on_delete=models.PROTECT,
        related_name="claims",
    )
    claim_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reward} for {self.donation.donor}"


class DonorAlert(models.Model):
    class Category(models.TextChoices):
        SHORTAGE = "shortage", "Shortage request"
        FORECAST = "forecast", "Inventory forecast"
        DONATION = "donation", "Donation verified"
        REWARD = "reward", "Reward"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="donor_alerts",
    )
    category = models.CharField(max_length=12, choices=Category.choices)
    message = models.CharField(max_length=500)
    dedupe_key = models.CharField(max_length=255)
    shortage_request = models.ForeignKey(
        "inventory.ShortageRequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="donor_alerts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    push_sent_at = models.DateTimeField(null=True, blank=True)
    push_pending = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "dedupe_key"),
                name="unique_donor_alert_dedupe_key",
            ),
        ]

    def __str__(self):
        return f"{self.get_category_display()} for {self.recipient}"