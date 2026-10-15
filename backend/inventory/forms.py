from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.utils import timezone

from .models import BloodInventory, Hospital, HospitalStaffProfile, ShortageRequest


class BloodInventoryForm(forms.ModelForm):
    class Meta:
        model = BloodInventory
        fields = ("blood_group", "units_available", "safe_threshold")
        widgets = {
            "blood_group": forms.Select(
                choices=(
                    ("A+", "A+"), ("A-", "A-"), ("B+", "B+"), ("B-", "B-"),
                    ("AB+", "AB+"), ("AB-", "AB-"), ("O+", "O+"), ("O-", "O-"),
                )
            ),
        }


class ShortageRequestForm(forms.ModelForm):
    class Meta:
        model = ShortageRequest
        fields = ("blood_group", "units_needed", "radius_km", "notes")
        widgets = {
            "radius_km": forms.NumberInput(attrs={"min": 1, "max": 50}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional context for the operations team"}),
        }


class ShortageResponseForm(forms.Form):
    donation_slot = forms.DateTimeField(
        required=False,
        label="Proposed donation date and time",
        help_text="Optional. Choose a future time before accepting; this response cannot be edited later.",
        input_formats=("%Y-%m-%dT%H:%M",),
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    def clean_donation_slot(self):
        donation_slot = self.cleaned_data["donation_slot"]
        if donation_slot and donation_slot <= timezone.now():
            raise forms.ValidationError("Choose a future date and time.")
        return donation_slot


class HospitalRegistrationForm(UserCreationForm):
    email = forms.EmailField()
    hospital_name = forms.CharField(max_length=255)
    registration_id = forms.CharField(max_length=100, label="Facility registration ID")
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))
    city = forms.CharField(max_length=100)
    job_title = forms.CharField(max_length=120, label="Your role")
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)

    class Meta:
        model = get_user_model()
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(
            (
                "hospital_name", "registration_id", "address", "city", "email",
                "job_title", "latitude", "longitude", "username", "password1", "password2",
            )
        )

    def clean_registration_id(self):
        registration_id = self.cleaned_data["registration_id"].strip()
        if Hospital.objects.filter(registration_id__iexact=registration_id).exists():
            raise forms.ValidationError("A facility with this registration ID is already registered.")
        return registration_id

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip()
        if commit:
            user.save()
            hospital = Hospital.objects.create(
                name=self.cleaned_data["hospital_name"].strip(),
                registration_id=self.cleaned_data["registration_id"],
                address=self.cleaned_data["address"].strip(),
                city=self.cleaned_data["city"].strip(),
                contact_email=user.email,
                latitude=self.cleaned_data["latitude"],
                longitude=self.cleaned_data["longitude"],
                approval_status=Hospital.ApprovalStatus.PENDING,
                is_active=False,
            )
            HospitalStaffProfile.objects.create(
                user=user,
                hospital=hospital,
                job_title=self.cleaned_data["job_title"].strip(),
                is_active=False,
            )
        return user