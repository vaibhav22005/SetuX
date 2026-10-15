from django.contrib import admin

from .models import DonorDevice, DonorProfile


@admin.register(DonorProfile)
class DonorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "blood_group", "city", "is_available", "latitude", "longitude", "updated_at")
    list_filter = ("blood_group", "is_available", "city")
    search_fields = ("user__username", "user__first_name", "user__last_name", "phone_number")


@admin.register(DonorDevice)
class DonorDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("user", "fcm_token", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False