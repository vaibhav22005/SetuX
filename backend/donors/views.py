import json

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventory.forms import ShortageResponseForm
from inventory.models import Hospital, ShortageRequest, ShortageResponse
from donors.services import donors_for_shortage
from .forms import DonorProfileForm, DonorRegistrationForm
from .models import DonorDevice, DonorProfile
from inventory.notifications import nearby_open_shortages_for_donor
from rewards.models import DonorAlert, RewardClaim
from rewards.services import claim_reward as claim_reward_service


def landing(request):
    return render(request, "landing.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("donors:dashboard")
    form = DonorRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("donors:dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    donor_profile = request.user.donorprofile
    accepted_responses = ShortageResponse.objects.filter(
        donor=donor_profile,
    ).select_related("shortage__hospital")
    accepted_shortage_ids = {response.shortage_id for response in accepted_responses}
    dashboard_shortages = [
        shortage
        for shortage in nearby_open_shortages_for_donor(donor_profile)
        if shortage.pk not in accepted_shortage_ids
    ][:8]
    for shortage in dashboard_shortages:
        shortage.response_form = ShortageResponseForm()

    context = {
        "profile": donor_profile,
        "firebase_web_enabled": settings.FIREBASE_WEB_ENABLED,
        "firebase_push_config": {
            "webConfig": settings.FIREBASE_WEB_CONFIG,
            "vapidKey": settings.FIREBASE_VAPID_KEY,
            "registerUrl": reverse("donors:register_push_device"),
            "unregisterUrl": reverse("donors:unregister_push_device"),
        },
        "registered_device_count": request.user.donor_devices.count(),
        "alerts": DonorAlert.objects.filter(recipient=request.user)[:8],
        "nearby_shortages": dashboard_shortages,
        "accepted_responses": accepted_responses,
        "reward_claims": RewardClaim.objects.filter(
            donation__donor__user=request.user,
        ).select_related("reward", "donation__hospital"),
    }
    return render(request, "dashboard.html", context)


@login_required
@require_POST
def accept_shortage(request, request_id):
    donor_profile = get_object_or_404(DonorProfile, user=request.user)
    if ShortageResponse.objects.filter(
        shortage_id=request_id,
        donor=donor_profile,
    ).exists():
        messages.info(request, "You have already accepted this request and cannot edit your response.")
        return redirect("donors:dashboard")

    form = ShortageResponseForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            "Please choose a future donation time, or leave the field blank.",
        )
        return redirect("donors:dashboard")

    with transaction.atomic():
        shortage = get_object_or_404(
            ShortageRequest.objects.select_for_update().select_related("hospital"),
            pk=request_id,
            status=ShortageRequest.Status.OPEN,
            hospital__is_active=True,
            hospital__approval_status=Hospital.ApprovalStatus.APPROVED,
        )
        response = ShortageResponse.objects.filter(
            shortage=shortage,
            donor=donor_profile,
        ).first()
        if response is not None:
            messages.info(request, "You have already accepted this request and cannot edit your response.")
            return redirect("donors:dashboard")

        if not any(
            donor.pk == donor_profile.pk
            for donor in donors_for_shortage(shortage)
        ):
            return render(request, "403.html", status=403)

        response = ShortageResponse.objects.create(
            shortage=shortage,
            donor=donor_profile,
        )
        proposed_slot = form.cleaned_data["donation_slot"]
        if proposed_slot:
            response.donation_slot = proposed_slot
            response.save(update_fields=["donation_slot"])

    if response.donation_slot:
        messages.success(
            request,
            "Shortage request accepted. The hospital can see your response and proposed time.",
        )
    else:
        messages.success(
            request,
            "Shortage request accepted. No donation time was proposed; this response cannot be edited.",
        )
    return redirect("donors:dashboard")


@login_required
def profile(request):
    donor_profile = request.user.donorprofile
    form = DonorProfileForm(request.POST or None, instance=donor_profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("donors:dashboard")
    return render(request, "profile.html", {"form": form, "profile": donor_profile})


@login_required
@require_POST
def mark_alerts_read(request):
    DonorAlert.objects.filter(recipient=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    return redirect("donors:dashboard")


@login_required
@require_POST
def register_push_device(request):
    if not settings.FIREBASE_WEB_ENABLED:
        return JsonResponse({"error": "Firebase web push is not configured."}, status=503)
    token = request.POST.get("token", "").strip()
    if not token or len(token) > 4096:
        return JsonResponse({"error": "A valid FCM device token is required."}, status=400)
    DonorDevice.objects.update_or_create(
        fcm_token=token,
        defaults={"user": request.user},
    )
    return JsonResponse({"registered": True})


@login_required
@require_POST
def unregister_push_device(request):
    token = request.POST.get("token", "").strip()
    if token:
        DonorDevice.objects.filter(user=request.user, fcm_token=token).delete()
    return JsonResponse({"registered": False})


def firebase_messaging_service_worker(request):
    if not settings.FIREBASE_WEB_ENABLED:
        return HttpResponse(status=404)
    config_json = json.dumps(settings.FIREBASE_WEB_CONFIG).replace("<", "\\u003c")
    response = render(
        request,
        "firebase-messaging-sw.js",
        {"firebase_web_config_json": config_json},
        content_type="application/javascript",
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def claim_reward(request, claim_id):
    claim = get_object_or_404(
        RewardClaim.objects.select_related("donation__donor__user", "reward"),
        pk=claim_id,
        donation__donor__user=request.user,
    )
    claim_reward_service(claim=claim, donor_user=request.user)
    messages.success(request, "Reward claimed. Show the claim code to the listed provider.")
    return redirect("donors:dashboard")