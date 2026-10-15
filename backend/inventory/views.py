from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from donors.services import donors_for_shortage

from .forms import BloodInventoryForm, HospitalRegistrationForm, ShortageRequestForm
from .models import (
    BloodInventory,
    Hospital,
    HospitalStaffProfile,
    ShortageRequest,
    ShortageResponse,
)
from .notifications import notify_shortage_donors
from .services import (
    summarize_inventory_risk_across_hospitals,
    summarize_inventory_risk_for_hospital,
)
from rewards.forms import DonationVerificationForm
from rewards.services import verify_donation


staff_required = user_passes_test(lambda user: user.is_staff, login_url="/login/")


def hospital_registration_submitted(request):
    return render(request, "registration/hospital_submitted.html")


def hospital_register(request):
    if request.user.is_authenticated:
        return redirect("hospital_dashboard")
    form = HospitalRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("hospital_registration_submitted")
    return render(request, "registration/hospital_register.html", {"form": form})


@staff_required
def control_room(request):
    low_stock_count = BloodInventory.objects.filter(
        units_available__lte=models.F("safe_threshold")
    ).count()
    context = {
        "hospital_count": Hospital.objects.filter(is_active=True).count(),
        "pending_hospital_count": Hospital.objects.filter(
            approval_status=Hospital.ApprovalStatus.PENDING
        ).count(),
        "low_stock_count": low_stock_count,
        "staff_count": HospitalStaffProfile.objects.filter(is_active=True).count(),
        "recent_inventory": BloodInventory.objects.select_related("hospital").order_by("-recorded_at")[:6],
        "open_shortages": ShortageRequest.objects.filter(
            status=ShortageRequest.Status.OPEN
        ).select_related("hospital")[:6],
        "forecast_risks": summarize_inventory_risk_across_hospitals(
            Hospital.objects.filter(is_active=True)
        )[:8],
    }
    return render(request, "operations/control_room.html", context)


@login_required(login_url="/hospital/login/")
def center_dashboard(request):
    staff_profile = HospitalStaffProfile.objects.filter(user=request.user).select_related("hospital").first()
    if staff_profile is None:
        return render(request, "403.html", status=403)
    if (
        not staff_profile.is_active
        or not staff_profile.hospital.is_active
        or staff_profile.hospital.approval_status != Hospital.ApprovalStatus.APPROVED
    ):
        return render(request, "operations/hospital_pending.html", {"hospital": staff_profile.hospital})
    hospital = staff_profile.hospital
    inventory_form = BloodInventoryForm(request.POST or None, prefix="inventory")
    shortage_form = ShortageRequestForm(request.POST or None, prefix="shortage")
    donation_form = DonationVerificationForm(
        request.POST if request.POST.get("form_type") == "donation" else None
    )
    if request.method == "POST" and request.POST.get("form_type") == "inventory" and inventory_form.is_valid():
        inventory = inventory_form.save(commit=False)
        inventory.hospital = hospital
        inventory.recorded_at = timezone.now()
        inventory.save()
        return redirect("hospital_dashboard")
    if request.method == "POST" and request.POST.get("form_type") == "donation" and donation_form.is_valid():
        try:
            verify_donation(
                donor_profile=donation_form.donor_profile,
                hospital=hospital,
                verified_by=request.user,
                donation_date=donation_form.cleaned_data["donation_date"],
                notes=donation_form.cleaned_data["notes"],
                reward=donation_form.cleaned_data["reward"],
            )
        except IntegrityError:
            donation_form.add_error(
                None,
                "A donation for this donor on that date has already been recorded.",
            )
        else:
            messages.success(request, "Donation verified and the donor has been notified.")
            return redirect("hospital_dashboard")

    inventory_logs = hospital.inventory_logs.order_by("-recorded_at")[:8]
    open_shortages = hospital.shortage_requests.filter(status=ShortageRequest.Status.OPEN)
    accepted_responses = ShortageResponse.objects.filter(
        shortage__hospital=hospital,
    ).select_related("donor__user", "shortage").order_by("-accepted_at")[:10]
    context = {
        "hospital": hospital,
        "staff_profile": staff_profile,
        "inventory_form": inventory_form,
        "shortage_form": shortage_form,
        "donation_form": donation_form,
        "inventory_logs": inventory_logs,
        "open_shortages": open_shortages[:6],
        "open_shortage_count": open_shortages.count(),
        "accepted_responses": accepted_responses,
        "forecast_risks": summarize_inventory_risk_for_hospital(hospital),
    }
    return render(request, "operations/center_dashboard.html", context)


@login_required(login_url="/hospital/login/")
def create_shortage(request):
    staff_profile = HospitalStaffProfile.objects.filter(
        user=request.user,
        is_active=True,
        hospital__is_active=True,
        hospital__approval_status=Hospital.ApprovalStatus.APPROVED,
    ).select_related("hospital").first()
    if staff_profile is None:
        return render(request, "403.html", status=403)
    if request.method != "POST":
        return redirect("hospital_dashboard")

    form = ShortageRequestForm(request.POST, prefix="shortage")
    if form.is_valid():
        shortage = form.save(commit=False)
        shortage.hospital = staff_profile.hospital
        shortage.requested_by = request.user
        shortage.save()
        notified_count = notify_shortage_donors(shortage)
        if notified_count:
            messages.success(
                request,
                f"Shortage request created. {notified_count} nearby matching donor(s) were notified.",
            )
        else:
            messages.info(
                request,
                "Shortage request created, but no available matching donors with saved locations "
                "were found in this radius.",
            )
        return redirect("inventory:shortage_detail", request_id=shortage.pk)

    return render(
        request,
        "operations/center_dashboard.html",
        {
            "hospital": staff_profile.hospital,
            "staff_profile": staff_profile,
            "inventory_form": BloodInventoryForm(prefix="inventory"),
            "shortage_form": form,
            "inventory_logs": staff_profile.hospital.inventory_logs.order_by("-recorded_at")[:8],
            "open_shortages": staff_profile.hospital.shortage_requests.filter(
                status=ShortageRequest.Status.OPEN
            )[:6],
            "open_shortage_count": staff_profile.hospital.shortage_requests.filter(
                status=ShortageRequest.Status.OPEN
            ).count(),
            "accepted_responses": ShortageResponse.objects.filter(
                shortage__hospital=staff_profile.hospital,
            ).select_related("donor__user", "shortage").order_by("-accepted_at")[:10],
            "forecast_risks": summarize_inventory_risk_for_hospital(staff_profile.hospital),
        },
        status=400,
    )


@login_required(login_url="/hospital/login/")
def shortage_detail(request, request_id):
    shortage = get_object_or_404(
        ShortageRequest.objects.select_related("hospital", "requested_by"),
        pk=request_id,
    )
    if not request.user.is_staff:
        profile = HospitalStaffProfile.objects.filter(
            user=request.user,
            is_active=True,
            hospital__is_active=True,
        ).first()
        if profile is None or profile.hospital_id != shortage.hospital_id:
            return render(request, "403.html", status=403)
    matches = donors_for_shortage(shortage)
    responses = shortage.responses.select_related("donor__user")
    return render(
        request,
        "operations/shortage_detail.html",
        {
            "shortage": shortage,
            "matches": matches,
            "match_count": len(matches),
            "responses": responses,
        },
    )