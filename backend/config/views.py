from django.contrib.auth.views import LoginView
from django.urls import reverse

from inventory.models import HospitalStaffProfile


class RoleAwareLoginView(LoginView):
    def get_default_redirect_url(self):
        user = self.request.user
        hospital_profile = getattr(user, "hospitalstaffprofile", None)
        if hospital_profile is not None:
            return reverse("hospital_dashboard")
        if user.is_staff:
            return reverse("inventory:control_room")
        return reverse("donors:dashboard")


class HospitalLoginView(LoginView):
    def form_valid(self, form):
        if not HospitalStaffProfile.objects.filter(user=form.get_user()).exists():
            form.add_error(None, "We could not find a hospital account for those credentials.")
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("hospital_dashboard")