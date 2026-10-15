from django.urls import path

from . import views


app_name = "inventory"

urlpatterns = [
    path("", views.control_room, name="control_room"),
    path("center/", views.center_dashboard, name="center_dashboard"),
    path("center/shortage/", views.create_shortage, name="create_shortage"),
    path("shortage/<int:request_id>/", views.shortage_detail, name="shortage_detail"),
]