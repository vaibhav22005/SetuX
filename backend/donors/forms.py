from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import DonorProfile


class DonorRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    blood_group = forms.ChoiceField(choices=DonorProfile.BloodGroup.choices)
    phone_number = forms.CharField(max_length=20, required=False)
    city = forms.CharField(max_length=100, required=False)
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False)

    class Meta:
        model = get_user_model()
        fields = (
            "username", "email", "password1", "password2", "blood_group",
            "phone_number", "city", "latitude", "longitude",
        )

    def clean(self):
        cleaned_data = super().clean()
        _validate_coordinates(cleaned_data, self.add_error)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            DonorProfile.objects.create(
                user=user,
                blood_group=self.cleaned_data["blood_group"],
                phone_number=self.cleaned_data["phone_number"],
                city=self.cleaned_data["city"],
                latitude=self.cleaned_data["latitude"],
                longitude=self.cleaned_data["longitude"],
            )
        return user


class DonorProfileForm(forms.ModelForm):
    class Meta:
        model = DonorProfile
        fields = ("phone_number", "city", "latitude", "longitude", "is_available")
        widgets = {
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "e.g. 18.5204"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "e.g. 73.8567"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        _validate_coordinates(cleaned_data, self.add_error)
        return cleaned_data


def _validate_coordinates(cleaned_data, add_error):
    latitude = cleaned_data.get("latitude")
    longitude = cleaned_data.get("longitude")
    if latitude is None and longitude is None:
        return
    if latitude is None or not -90 <= latitude <= 90:
        add_error("latitude", "Enter a latitude between -90 and 90.")
    if longitude is None or not -180 <= longitude <= 180:
        add_error("longitude", "Enter a longitude between -180 and 180.")