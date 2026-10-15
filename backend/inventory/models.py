from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings
from django.db import models


class Hospital(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=255)
    registration_id = models.CharField(max_length=100, unique=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    contact_email = models.EmailField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class HospitalStaffProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="staff_profiles")
    job_title = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.hospital}"


class ShortageRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    BLOOD_GROUP_CHOICES = (
        ("A+", "A+"), ("A-", "A-"), ("B+", "B+"), ("B-", "B-"),
        ("AB+", "AB+"), ("AB-", "AB-"), ("O+", "O+"), ("O-", "O-"),
    )

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="shortage_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shortage_requests",
    )
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUP_CHOICES)
    units_needed = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    radius_km = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.hospital} - {self.blood_group} ({self.status})"


class ShortageResponse(models.Model):
    shortage = models.ForeignKey(
        ShortageRequest,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    donor = models.ForeignKey(
        "donors.DonorProfile",
        on_delete=models.CASCADE,
        related_name="shortage_responses",
    )
    accepted_at = models.DateTimeField(auto_now_add=True)
    donation_slot = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["accepted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("shortage", "donor"),
                name="unique_donor_shortage_response",
            ),
        ]

    def __str__(self):
        return f"{self.donor} accepted {self.shortage}"


class BloodInventory(models.Model):
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="inventory_logs")
    blood_group = models.CharField(max_length=3)
    units_available = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    safe_threshold = models.PositiveIntegerField(default=5)
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["hospital", "blood_group", "-recorded_at"]),
        ]

    def __str__(self):
        return f"{self.hospital} - {self.blood_group}: {self.units_available} units"