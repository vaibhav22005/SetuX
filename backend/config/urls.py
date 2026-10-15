from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from inventory.views import center_dashboard, hospital_registration_submitted, hospital_register

from .views import HospitalLoginView, RoleAwareLoginView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("donors.urls")),
    path("operations/", include("inventory.urls")),
    path("hospital/dashboard/", center_dashboard, name="hospital_dashboard"),
    path("hospital/register/", hospital_register, name="hospital_register"),
    path("hospital/register/submitted/", hospital_registration_submitted, name="hospital_registration_submitted"),
    path("hospital/login/", HospitalLoginView.as_view(template_name="registration/hospital_login.html"), name="hospital_login"),
    path("login/", RoleAwareLoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]