from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from donors.models import DonorDevice, DonorProfile
from inventory.models import Hospital
from rewards.models import DonorAlert

from .forms import DonorProfileForm
from .services import nearby_available_donors


class DonorProfileTest(TestCase):
    def test_profile_is_created_without_seed_data(self):
        user = get_user_model().objects.create_user(username="donor")
        profile = DonorProfile.objects.create(
            user=user,
            blood_group=DonorProfile.BloodGroup.O_POSITIVE,
        )
        self.assertEqual(str(profile), "donor (O+)")


class DonorViewTest(TestCase):
    def test_landing_page_is_public(self):
        response = self.client.get(reverse("donors:landing"))
        self.assertEqual(response.status_code, 200)

    def test_registration_offers_device_location_capture(self):
        response = self.client.get(reverse("donors:register"))
        self.assertContains(response, "Use my current location")
        self.assertContains(response, "js/location.js")
        self.assertContains(response, 'id="id_latitude"')
        self.assertContains(response, 'id="id_longitude"')

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("donors:dashboard"))
        self.assertRedirects(response, "/login/?next=/dashboard/")

    def test_profile_offers_device_location_capture(self):
        user = get_user_model().objects.create_user(username="location-donor")
        DonorProfile.objects.create(user=user, blood_group=DonorProfile.BloodGroup.O_POSITIVE)
        self.client.force_login(user)

        response = self.client.get(reverse("donors:profile"))

        self.assertContains(response, "Use my current location")
        self.assertContains(response, "js/location.js")

    def test_dashboard_shows_and_marks_donor_alerts_read(self):
        user = get_user_model().objects.create_user(username="alerts-donor")
        DonorProfile.objects.create(user=user, blood_group=DonorProfile.BloodGroup.O_POSITIVE)
        alert = DonorAlert.objects.create(
            recipient=user,
            category=DonorAlert.Category.SHORTAGE,
            message="A nearby center needs O+ donors.",
            dedupe_key="test-shortage-alert",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("donors:dashboard"))

        self.assertContains(response, "A nearby center needs O+ donors.")
        response = self.client.post(reverse("donors:mark_alerts_read"))
        self.assertRedirects(response, reverse("donors:dashboard"), fetch_redirect_response=False)
        alert.refresh_from_db()
        self.assertIsNotNone(alert.read_at)

    @override_settings(FIREBASE_ENABLED=True, FIREBASE_WEB_ENABLED=True)
    def test_donor_can_register_and_remove_browser_push_token(self):
        user = get_user_model().objects.create_user(username="push-donor")
        DonorProfile.objects.create(user=user, blood_group=DonorProfile.BloodGroup.O_POSITIVE)
        self.client.force_login(user)

        response = self.client.post(
            reverse("donors:register_push_device"),
            {"token": "test-fcm-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(DonorDevice.objects.filter(user=user, fcm_token="test-fcm-token").exists())
        response = self.client.post(
            reverse("donors:unregister_push_device"),
            {"token": "test-fcm-token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DonorDevice.objects.filter(user=user).exists())

    @override_settings(
        FIREBASE_ENABLED=True,
        FIREBASE_WEB_ENABLED=True,
        FIREBASE_WEB_CONFIG={
            "apiKey": "public-test-key",
            "authDomain": "test.firebaseapp.com",
            "projectId": "test-project",
            "storageBucket": "test.appspot.com",
            "messagingSenderId": "123",
            "appId": "1:123:web:abc",
        },
    )
    def test_firebase_service_worker_is_served_with_public_config(self):
        response = self.client.get(reverse("donors:firebase_messaging_service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertIn(b"test-project", response.content)


class DonorLocationFormTest(TestCase):
    def test_location_is_validated(self):
        form = DonorProfileForm(data={"city": "Pune", "latitude": "18.5204", "longitude": "73.8567"})
        self.assertTrue(form.is_valid())

    def test_invalid_location_is_rejected(self):
        form = DonorProfileForm(data={"latitude": "95", "longitude": "200"})
        self.assertFalse(form.is_valid())


class DonorMatchingFallbackTest(TestCase):
    def test_sqlite_fallback_returns_only_nearby_available_matching_donors(self):
        hospital = Hospital.objects.create(
            name="Local Match Center",
            registration_id="LOCAL-MATCH-001",
            address="Local address",
            city="Pune",
            latitude=18.5204,
            longitude=73.8567,
        )
        nearby_user = get_user_model().objects.create_user(username="nearby-donor")
        nearby = DonorProfile.objects.create(
            user=nearby_user,
            blood_group="O+",
            latitude=18.5210,
            longitude=73.8570,
        )
        far_user = get_user_model().objects.create_user(username="far-donor")
        DonorProfile.objects.create(
            user=far_user,
            blood_group="O+",
            latitude=19.0760,
            longitude=72.8777,
        )
        unavailable_user = get_user_model().objects.create_user(username="unavailable-donor")
        DonorProfile.objects.create(
            user=unavailable_user,
            blood_group="O+",
            latitude=18.5205,
            longitude=73.8568,
            is_available=False,
        )

        matches = nearby_available_donors(hospital, "O+", radius_km=10)

        self.assertEqual(matches, [nearby])