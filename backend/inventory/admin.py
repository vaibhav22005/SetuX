from django.contrib import admin
from django.db import transaction

from .models import BloodInventory, Hospital, HospitalStaffProfile, ShortageRequest


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ("name", "registration_id", "city", "approval_status", "is_active")
    list_filter = ("approval_status", "city")
    search_fields = ("name", "registration_id", "city")
    readonly_fields = ("approval_status", "is_active")
    actions = ("approve_registrations", "reject_registrations")

    @admin.action(description="Approve selected healthcare center registrations")
    def approve_registrations(self, request, queryset):
        with transaction.atomic():
            hospital_ids = list(queryset.values_list("pk", flat=True))
            updated = Hospital.objects.filter(pk__in=hospital_ids).update(
                approval_status=Hospital.ApprovalStatus.APPROVED,
                is_active=True,
            )
            HospitalStaffProfile.objects.filter(hospital_id__in=hospital_ids).update(is_active=True)
        self.message_user(request, f"Approved {updated} healthcare center registration(s).")

    @admin.action(description="Reject selected healthcare center registrations")
    def reject_registrations(self, request, queryset):
        with transaction.atomic():
            hospital_ids = list(queryset.values_list("pk", flat=True))
            updated = Hospital.objects.filter(pk__in=hospital_ids).update(
                approval_status=Hospital.ApprovalStatus.REJECTED,
                is_active=False,
            )
            HospitalStaffProfile.objects.filter(hospital_id__in=hospital_ids).update(is_active=False)
        self.message_user(request, f"Rejected {updated} healthcare center registration(s).")


@admin.register(BloodInventory)
class BloodInventoryAdmin(admin.ModelAdmin):
    list_display = ("hospital", "blood_group", "units_available", "safe_threshold", "recorded_at")
    list_filter = ("blood_group", "hospital")
    search_fields = ("hospital__name",)
    date_hierarchy = "recorded_at"


@admin.register(HospitalStaffProfile)
class HospitalStaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "hospital", "job_title", "is_active")
    list_filter = ("hospital", "is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "hospital__name")


@admin.register(ShortageRequest)
class ShortageRequestAdmin(admin.ModelAdmin):
    list_display = ("hospital", "blood_group", "units_needed", "radius_km", "status", "created_at")
    list_filter = ("status", "blood_group", "hospital")
    search_fields = ("hospital__name", "requested_by__username", "notes")
    readonly_fields = ("created_at",)