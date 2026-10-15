from django.contrib import admin

from .models import DonorAlert, DonationRecord, Reward, RewardClaim


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ("title", "reward_type", "provider_name", "is_active")
    list_filter = ("reward_type", "is_active")
    search_fields = ("title", "provider_name")


@admin.register(DonationRecord)
class DonationRecordAdmin(admin.ModelAdmin):
    list_display = ("donor", "hospital", "donation_date", "verified_by", "created_at")
    list_filter = ("hospital", "donation_date")
    search_fields = ("donor__user__username", "donor__user__email", "hospital__name")
    readonly_fields = ("donor", "hospital", "verified_by", "donation_date", "notes", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(RewardClaim)
class RewardClaimAdmin(admin.ModelAdmin):
    list_display = ("reward", "donation", "claim_code", "claimed_at", "created_at")
    list_filter = ("reward", "claimed_at")
    search_fields = ("donation__donor__user__username", "reward__title", "claim_code")
    readonly_fields = ("donation", "reward", "claim_code", "claimed_at", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(DonorAlert)
class DonorAlertAdmin(admin.ModelAdmin):
    list_display = ("recipient", "category", "created_at", "read_at")
    list_filter = ("category", "read_at")
    search_fields = ("recipient__username", "message")
    readonly_fields = ("recipient", "category", "message", "dedupe_key", "shortage_request", "created_at", "read_at")

    def has_add_permission(self, request):
        return False