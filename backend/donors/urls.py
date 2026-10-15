from django.urls import path

from . import views


app_name = "donors"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("register/", views.register, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("shortages/<int:request_id>/accept/", views.accept_shortage, name="accept_shortage"),
    path("profile/", views.profile, name="profile"),
    path("alerts/read/", views.mark_alerts_read, name="mark_alerts_read"),
    path("devices/register/", views.register_push_device, name="register_push_device"),
    path("devices/unregister/", views.unregister_push_device, name="unregister_push_device"),
    path("rewards/<int:claim_id>/claim/", views.claim_reward, name="claim_reward"),
    path("firebase-messaging-sw.js", views.firebase_messaging_service_worker, name="firebase_messaging_service_worker"),
]