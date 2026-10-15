from django import forms
from django.utils import timezone

from donors.models import DonorProfile

from .models import Reward


class DonationVerificationForm(forms.Form):
    donor_username = forms.CharField(
        max_length=150,
        label="Donor username",
        help_text="Enter the donor's SetuX username exactly as shown on their profile.",
    )
    donation_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    reward = forms.ModelChoiceField(
        queryset=Reward.objects.none(),
        required=False,
        empty_label="No reward to issue",
        help_text="Only active, non-cash rewards can be issued.",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reward"].queryset = Reward.objects.filter(is_active=True)

    def clean_donor_username(self):
        username = self.cleaned_data["donor_username"].strip()
        try:
            self.donor_profile = DonorProfile.objects.select_related("user").get(
                user__username__iexact=username,
            )
        except DonorProfile.DoesNotExist as exc:
            raise forms.ValidationError("No donor profile was found for that username.") from exc
        return username

    def clean_donation_date(self):
        donation_date = self.cleaned_data["donation_date"]
        if donation_date > timezone.localdate():
            raise forms.ValidationError("Donation date cannot be in the future.")
        return donation_date
