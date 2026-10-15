from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as django_timezone

from donors.models import DonorProfile

from .models import BloodInventory, Hospital, HospitalStaffProfile, ShortageRequest, ShortageResponse
from .services import forecast_inventory_risk_for_group, save_synthetic_inventory_history
from rewards.models import DonorAlert, DonationRecord, Reward, RewardClaim


class InventoryTest(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_user(
            username="site-admin",
            is_staff=True,
            is_superuser=True,
            email="admin@example.org",
        )

    def test_hospital_registration_offers_device_location_capture(self):
        response = self.client.get(reverse("hospital_register"))

        self.assertContains(response, "Use my current location")
        self.assertContains(response, "js/location.js")
        self.assertContains(response, 'id="id_latitude"')
        self.assertContains(response, 'id="id_longitude"')

    def test_inventory_belongs_to_hospital(self):
        hospital = Hospital.objects.create(
            name="Example Hospital",
            registration_id="EXAMPLE-001",
            address="Example address",
            city="Pune",
        )
        inventory = BloodInventory.objects.create(
            hospital=hospital,
            blood_group="O+",
            units_available=10,
            recorded_at=datetime.now(timezone.utc),
        )
        self.assertEqual(inventory.hospital, hospital)

    def test_staff_can_open_shortage_request_for_assigned_hospital(self):
        user = get_user_model().objects.create_user(username="center-staff", is_staff=True)
        hospital = Hospital.objects.create(
            name="Request Hospital",
            registration_id="REQUEST-001",
            address="Request address",
            city="Pune",
            latitude=18.5204,
            longitude=73.8567,
        )
        donor_user = get_user_model().objects.create_user(username="request-matching-donor")
        donor_profile = DonorProfile.objects.create(
            user=donor_user,
            blood_group="O+",
            latitude=18.5210,
            longitude=73.8570,
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital)
        self.client.force_login(user)
        with patch("inventory.notifications.donors_for_shortage", return_value=[donor_profile]):
            response = self.client.post(
                reverse("inventory:create_shortage"),
                {
                    "form_type": "shortage",
                    "shortage-blood_group": "O+",
                    "shortage-units_needed": 2,
                    "shortage-radius_km": 5,
                    "shortage-notes": "Urgent request",
                },
            )
        self.assertEqual(response.status_code, 302)
        shortage = ShortageRequest.objects.get(hospital=hospital)
        self.assertTrue(
            DonorAlert.objects.filter(
                recipient=donor_user,
                shortage_request=shortage,
                category=DonorAlert.Category.SHORTAGE,
            ).exists()
        )
        alert = DonorAlert.objects.get(recipient=donor_user, shortage_request=shortage)
        self.assertIn("Request address, Pune", alert.message)

        self.client.force_login(donor_user)
        with patch(
            "donors.views.nearby_open_shortages_for_donor",
            return_value=[shortage],
        ):
            donor_dashboard = self.client.get(reverse("donors:dashboard"))
        self.assertContains(donor_dashboard, "Request Hospital")
        self.assertContains(donor_dashboard, "Request address, Pune")
        self.assertContains(donor_dashboard, "2")

    def test_donor_dashboard_shows_existing_nearby_request_without_alert(self):
        donor_user = get_user_model().objects.create_user(username="legacy-request-donor")
        DonorProfile.objects.create(
            user=donor_user,
            blood_group="O+",
            latitude=18.5210,
            longitude=73.8570,
        )
        hospital = Hospital.objects.create(
            name="Existing Request Center",
            registration_id="REQUEST-EXISTING-001",
            address="Request address",
            city="Pune",
            latitude=18.5204,
            longitude=73.8567,
        )
        ShortageRequest.objects.create(
            hospital=hospital,
            blood_group="O+",
            units_needed=3,
            radius_km=5,
        )
        self.client.force_login(donor_user)

        response = self.client.get(reverse("donors:dashboard"))

        self.assertContains(response, "Existing Request Center")
        self.assertEqual(len(response.context["nearby_shortages"]), 1)

    def test_eligible_donor_can_accept_and_propose_time_visible_to_hospital(self):
        donor_user = get_user_model().objects.create_user(username="accepting-donor")
        donor_profile = DonorProfile.objects.create(
            user=donor_user,
            blood_group="O+",
            latitude=18.5210,
            longitude=73.8570,
        )
        hospital = Hospital.objects.create(
            name="Acceptance Hospital",
            registration_id="ACCEPT-001",
            address="22 Care Street",
            city="Pune",
            latitude=18.5204,
            longitude=73.8567,
        )
        shortage = ShortageRequest.objects.create(
            hospital=hospital,
            blood_group="O+",
            units_needed=2,
        )
        proposed_slot = (django_timezone.now() + timedelta(days=2)).replace(
            second=0,
            microsecond=0,
        )
        slot_input = django_timezone.localtime(proposed_slot).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(donor_user)

        with patch("donors.views.donors_for_shortage", return_value=[donor_profile]):
            response = self.client.post(
                reverse("donors:accept_shortage", args=[shortage.pk]),
                {"donation_slot": slot_input},
            )

        self.assertRedirects(response, reverse("donors:dashboard"), fetch_redirect_response=False)
        donor_response = ShortageResponse.objects.get(shortage=shortage, donor=donor_profile)
        self.assertIsNotNone(donor_response.accepted_at)
        self.assertEqual(
            django_timezone.localtime(donor_response.donation_slot),
            proposed_slot,
        )

        with patch("donors.views.nearby_open_shortages_for_donor", return_value=[]):
            donor_dashboard = self.client.get(reverse("donors:dashboard"))
        self.assertContains(donor_dashboard, "Acceptance Hospital")
        self.assertContains(donor_dashboard, "22 Care Street, Pune")
        self.assertContains(donor_dashboard, "View map and route")
        self.assertContains(donor_dashboard, "data-hospital-directions")
        self.assertContains(donor_dashboard, "hospital_directions.js")
        self.assertContains(donor_dashboard, "data-hospital-latitude=\"18.520400\"")
        self.assertContains(donor_dashboard, "data-hospital-longitude=\"73.856700\"")
        self.assertContains(donor_dashboard, "Accepted requests")
        self.assertContains(donor_dashboard, "Accepted")
        self.assertNotContains(donor_dashboard, "Update proposed time")
        self.assertContains(
            donor_dashboard,
            proposed_slot.strftime("%d %b %Y"),
        )

        updated_slot = proposed_slot + timedelta(days=1)
        updated_slot_input = django_timezone.localtime(updated_slot).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("donors:accept_shortage", args=[shortage.pk]),
            {"donation_slot": updated_slot_input},
        )
        self.assertRedirects(response, reverse("donors:dashboard"), fetch_redirect_response=False)
        donor_response.refresh_from_db()
        self.assertEqual(
            django_timezone.localtime(donor_response.donation_slot),
            proposed_slot,
        )

        hospital_user = get_user_model().objects.create_user(
            username="acceptance-hospital-staff",
            is_staff=True,
        )
        HospitalStaffProfile.objects.create(user=hospital_user, hospital=hospital)
        self.client.force_login(hospital_user)
        with patch("inventory.views.donors_for_shortage", return_value=[]):
            hospital_detail = self.client.get(
                reverse("inventory:shortage_detail", args=[shortage.pk])
            )

        self.assertContains(hospital_detail, "Accepted requests and proposed times")
        self.assertContains(hospital_detail, "accepting-donor")
        self.assertContains(hospital_detail, proposed_slot.strftime("%d %b %Y"))

        center_dashboard = self.client.get(reverse("hospital_dashboard"))
        self.assertContains(center_dashboard, "Accepted donor requests")
        self.assertContains(center_dashboard, "accepting-donor")
        self.assertContains(center_dashboard, proposed_slot.strftime("%d %b %Y"))

    def test_unmatched_donor_cannot_accept_shortage(self):
        donor_user = get_user_model().objects.create_user(username="unmatched-donor")
        donor_profile = DonorProfile.objects.create(user=donor_user, blood_group="O+")
        hospital = Hospital.objects.create(
            name="Restricted Hospital",
            registration_id="RESTRICTED-001",
            address="Restricted address",
            city="Pune",
            latitude=18.5204,
            longitude=73.8567,
        )
        shortage = ShortageRequest.objects.create(
            hospital=hospital,
            blood_group="O+",
            units_needed=1,
        )
        self.client.force_login(donor_user)

        with patch("donors.views.donors_for_shortage", return_value=[]):
            response = self.client.post(
                reverse("donors:accept_shortage", args=[shortage.pk]),
                {},
            )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            ShortageResponse.objects.filter(shortage=shortage, donor=donor_profile).exists()
        )

    def test_hospital_staff_login_redirects_to_hospital_dashboard(self):
        user = get_user_model().objects.create_user(
            username="hospital-login",
            password="test-password",
            is_staff=True,
        )
        hospital = Hospital.objects.create(
            name="Login Hospital",
            registration_id="LOGIN-001",
            address="Login address",
            city="Pune",
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital)

        response = self.client.post(
            reverse("login"),
            {"username": "hospital-login", "password": "test-password"},
        )

        self.assertRedirects(response, reverse("hospital_dashboard"), fetch_redirect_response=False)

    def test_hospital_dashboard_requires_an_assignment(self):
        user = get_user_model().objects.create_user(username="unassigned-staff", is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse("hospital_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_assigned_hospital_staff_can_open_dedicated_dashboard(self):
        user = get_user_model().objects.create_user(username="assigned-staff", is_staff=True)
        hospital = Hospital.objects.create(
            name="Assigned Hospital",
            registration_id="ASSIGNED-001",
            address="Assigned address",
            city="Pune",
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital)
        self.client.force_login(user)

        response = self.client.get(reverse("hospital_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Hospital")

    def test_hospital_dashboard_counts_all_open_shortage_requests(self):
        user = get_user_model().objects.create_user(username="shortage-count-staff", is_staff=True)
        hospital = Hospital.objects.create(
            name="Shortage Count Hospital",
            registration_id="SHORTAGE-COUNT-001",
            address="Shortage count address",
            city="Pune",
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital)
        ShortageRequest.objects.create(hospital=hospital, blood_group="O+", units_needed=2)
        ShortageRequest.objects.create(hospital=hospital, blood_group="A+", units_needed=1)
        ShortageRequest.objects.create(
            hospital=hospital,
            blood_group="B+",
            units_needed=1,
            status=ShortageRequest.Status.CLOSED,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("hospital_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["open_shortage_count"], 2)
        self.assertContains(response, "<strong>2</strong>", html=True)
        self.assertContains(response, "open shortage requests")

    def test_hospital_signup_creates_pending_non_staff_account(self):
        response = self.client.post(
            reverse("hospital_register"),
            {
                "hospital_name": "New Care Center",
                "registration_id": "NEW-CENTER-001",
                "address": "10 Example Road",
                "city": "Pune",
                "email": "manager@example.org",
                "job_title": "Blood Bank Manager",
                "latitude": "18.5204",
                "longitude": "73.8567",
                "username": "new-center-manager",
                "password1": "Safe-password-872!",
                "password2": "Safe-password-872!",
            },
        )

        self.assertRedirects(
            response,
            reverse("hospital_registration_submitted"),
            fetch_redirect_response=False,
        )
        user = get_user_model().objects.get(username="new-center-manager")
        profile = HospitalStaffProfile.objects.get(user=user)
        self.assertFalse(user.is_staff)
        self.assertFalse(profile.is_active)
        self.assertFalse(profile.hospital.is_active)
        self.assertEqual(profile.hospital.approval_status, Hospital.ApprovalStatus.PENDING)

    def test_admin_can_approve_hospital_registration(self):
        user = get_user_model().objects.create_user(username="pending-center-manager")
        hospital = Hospital.objects.create(
            name="Pending Center",
            registration_id="PENDING-APPROVE-001",
            address="Pending address",
            city="Pune",
            is_active=False,
        )
        profile = HospitalStaffProfile.objects.create(
            user=user,
            hospital=hospital,
            is_active=False,
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("admin:inventory_hospital_changelist"),
            {
                "action": "approve_registrations",
                "index": "0",
                "_selected_action": [str(hospital.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        hospital.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(hospital.approval_status, Hospital.ApprovalStatus.APPROVED)
        self.assertTrue(hospital.is_active)
        self.assertTrue(profile.is_active)

    def test_operations_dashboard_links_pending_center_requests(self):
        Hospital.objects.create(
            name="Awaiting Review",
            registration_id="PENDING-DASHBOARD-001",
            address="Pending address",
            city="Pune",
            approval_status=Hospital.ApprovalStatus.PENDING,
            is_active=False,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("inventory:control_room"))

        self.assertContains(response, "Pending verification")
        self.assertContains(response, "?approval_status__exact=pending")
        self.assertEqual(response.context["pending_hospital_count"], 1)

    def test_admin_can_reject_hospital_registration(self):
        user = get_user_model().objects.create_user(username="rejected-center-manager")
        hospital = Hospital.objects.create(
            name="Rejected Center",
            registration_id="PENDING-REJECT-001",
            address="Pending address",
            city="Pune",
            is_active=False,
        )
        profile = HospitalStaffProfile.objects.create(
            user=user,
            hospital=hospital,
            is_active=False,
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("admin:inventory_hospital_changelist"),
            {
                "action": "reject_registrations",
                "index": "0",
                "_selected_action": [str(hospital.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        hospital.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(hospital.approval_status, Hospital.ApprovalStatus.REJECTED)
        self.assertFalse(hospital.is_active)
        self.assertFalse(profile.is_active)

    def test_rejected_hospital_sees_rejection_status_instead_of_pending(self):
        user = get_user_model().objects.create_user(username="rejected-center-login", password="test-password")
        hospital = Hospital.objects.create(
            name="Rejected Center",
            registration_id="REJECTED-STATUS-001",
            address="Pending address",
            city="Pune",
            approval_status=Hospital.ApprovalStatus.REJECTED,
            is_active=False,
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital, is_active=False)
        self.client.force_login(user)

        response = self.client.get(reverse("hospital_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "was not approved")
        self.assertNotContains(response, "is being verified")

    def test_pending_hospital_can_sign_in_and_see_review_status(self):
        user = get_user_model().objects.create_user(
            username="pending-center",
            password="test-password-872!",
            is_staff=False,
        )
        hospital = Hospital.objects.create(
            name="Pending Center",
            registration_id="PENDING-001",
            address="Pending address",
            city="Pune",
            is_active=False,
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital, is_active=False)

        response = self.client.post(
            reverse("hospital_login"),
            {"username": "pending-center", "password": "test-password-872!"},
        )
        self.assertRedirects(response, reverse("hospital_dashboard"), fetch_redirect_response=False)

        response = self.client.get(reverse("hospital_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "being verified")
        self.assertContains(response, "Hospital dashboard")

    def test_donor_account_cannot_use_hospital_login(self):
        user = get_user_model().objects.create_user(
            username="donor-at-hospital-login",
            password="test-password-872!",
        )

        response = self.client.post(
            reverse("hospital_login"),
            {"username": user.username, "password": "test-password-872!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not find a hospital account")

    def test_synthetic_history_is_one_year_long_and_idempotent(self):
        hospital = Hospital.objects.create(
            name="Forecast Hospital",
            registration_id="FORECAST-001",
            address="Forecast address",
            city="Pune",
        )

        created = save_synthetic_inventory_history(hospital, blood_group="O+", days=365)
        repeated_created = save_synthetic_inventory_history(hospital, blood_group="O+", days=365)

        self.assertEqual(created, 365)
        self.assertEqual(repeated_created, 0)
        self.assertEqual(
            BloodInventory.objects.filter(hospital=hospital, blood_group="O+").count(),
            365,
        )

    def test_forecast_uses_the_latest_history_and_predicts_linear_trend(self):
        hospital = Hospital.objects.create(
            name="Forecast Hospital",
            registration_id="FORECAST-002",
            address="Forecast address",
            city="Pune",
        )
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        records = [
            BloodInventory(
                hospital=hospital,
                blood_group="O+",
                units_available=1000 if offset == 0 else 100 - offset,
                safe_threshold=5,
                recorded_at=start + timedelta(days=offset),
            )
            for offset in range(91)
        ]
        BloodInventory.objects.bulk_create(records)

        result = forecast_inventory_risk_for_group(hospital, "O+", days_ahead=3)

        self.assertEqual(result["current_units"], 10)
        self.assertEqual(
            [item["predicted_units"] for item in result["forecast"]],
            [9, 8, 7],
        )

    def test_center_dashboard_displays_forecast_outlook(self):
        user = get_user_model().objects.create_user(username="forecast-staff")
        hospital = Hospital.objects.create(
            name="Forecast Dashboard Center",
            registration_id="FORECAST-003",
            address="Forecast address",
            city="Pune",
        )
        HospitalStaffProfile.objects.create(user=user, hospital=hospital)
        BloodInventory.objects.create(
            hospital=hospital,
            blood_group="O+",
            units_available=3,
            safe_threshold=5,
            recorded_at=datetime.now(timezone.utc),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("hospital_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory outlook")
        self.assertContains(response, "O+")
        self.assertEqual(response.context["forecast_risks"][0]["risk_level"], "high")

    def test_hospital_staff_verifies_donation_and_issues_active_reward(self):
        staff = get_user_model().objects.create_user(username="verifying-staff")
        hospital = Hospital.objects.create(
            name="Verification Center",
            registration_id="VERIFY-001",
            address="Verification address",
            city="Pune",
        )
        HospitalStaffProfile.objects.create(user=staff, hospital=hospital)
        donor_user = get_user_model().objects.create_user(username="verified-donor")
        donor_profile = DonorProfile.objects.create(
            user=donor_user,
            blood_group="O+",
        )
        reward = Reward.objects.create(
            title="Health checkup",
            description="A non-cash post-donation health check.",
            reward_type=Reward.RewardType.HEALTH_CHECKUP,
        )
        self.client.force_login(staff)
        donation_date = django_timezone.localdate()

        response = self.client.post(
            reverse("hospital_dashboard"),
            {
                "form_type": "donation",
                "donor_username": donor_user.username,
                "donation_date": donation_date.isoformat(),
                "reward": str(reward.pk),
                "notes": "Verified at center",
            },
        )

        self.assertRedirects(response, reverse("hospital_dashboard"), fetch_redirect_response=False)
        donation = DonationRecord.objects.get(donor=donor_profile, hospital=hospital)
        claim = RewardClaim.objects.get(donation=donation, reward=reward)
        donor_profile.refresh_from_db()
        self.assertEqual(donor_profile.last_donation_date, donation_date)
        self.assertEqual(
            DonorAlert.objects.filter(recipient=donor_user).count(),
            2,
        )
        self.assertIsNotNone(claim.claim_code)

    def test_duplicate_donation_is_rejected(self):
        staff = get_user_model().objects.create_user(username="duplicate-verifier")
        hospital = Hospital.objects.create(
            name="Duplicate Center",
            registration_id="VERIFY-002",
            address="Verification address",
            city="Pune",
        )
        HospitalStaffProfile.objects.create(user=staff, hospital=hospital)
        donor_user = get_user_model().objects.create_user(username="duplicate-donor")
        donor_profile = DonorProfile.objects.create(user=donor_user, blood_group="O+")
        donation_date = django_timezone.localdate()
        DonationRecord.objects.create(
            donor=donor_profile,
            hospital=hospital,
            verified_by=staff,
            donation_date=donation_date,
        )
        self.client.force_login(staff)

        response = self.client.post(
            reverse("hospital_dashboard"),
            {
                "form_type": "donation",
                "donor_username": donor_user.username,
                "donation_date": donation_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already been recorded")
        self.assertEqual(DonationRecord.objects.filter(donor=donor_profile).count(), 1)

    def test_donor_can_claim_only_their_own_reward(self):
        donor_user = get_user_model().objects.create_user(username="claiming-donor")
        donor_profile = DonorProfile.objects.create(user=donor_user, blood_group="O+")
        hospital = Hospital.objects.create(
            name="Claim Center",
            registration_id="CLAIM-001",
            address="Claim address",
            city="Pune",
        )
        verifier = get_user_model().objects.create_user(username="claim-verifier")
        reward = Reward.objects.create(
            title="Doctor consultation",
            description="A non-cash consultation.",
            reward_type=Reward.RewardType.DOCTOR_CONSULTATION,
        )
        donation = DonationRecord.objects.create(
            donor=donor_profile,
            hospital=hospital,
            verified_by=verifier,
            donation_date=django_timezone.localdate() - timedelta(days=1),
        )
        claim = RewardClaim.objects.create(donation=donation, reward=reward)

        self.client.force_login(donor_user)
        response = self.client.post(reverse("donors:claim_reward", args=[claim.pk]))

        self.assertRedirects(response, reverse("donors:dashboard"), fetch_redirect_response=False)
        claim.refresh_from_db()
        self.assertIsNotNone(claim.claimed_at)
        self.assertTrue(
            DonorAlert.objects.filter(
                recipient=donor_user,
                dedupe_key=f"reward-claimed:{claim.pk}",
            ).exists()
        )

    def test_shortage_alert_task_is_idempotent(self):
        from inventory.tasks import notify_open_shortages

        donor_user = get_user_model().objects.create_user(username="shortage-alert-donor")
        donor_profile = DonorProfile.objects.create(user=donor_user, blood_group="O+")
        hospital = Hospital.objects.create(
            name="Alert Center",
            registration_id="ALERT-001",
            address="Alert address",
            city="Pune",
        )
        shortage = ShortageRequest.objects.create(
            hospital=hospital,
            blood_group="O+",
            units_needed=2,
            radius_km=5,
        )
        with patch("inventory.notifications.donors_for_shortage", return_value=[donor_profile]):
            notify_open_shortages.run()
            notify_open_shortages.run()

        self.assertEqual(
            DonorAlert.objects.filter(
                recipient=donor_user,
                shortage_request=shortage,
            ).count(),
            1,
        )

    def test_daily_forecast_task_creates_deduplicated_risk_alerts(self):
        from inventory.tasks import dispatch_inventory_risk_alerts

        donor_user = get_user_model().objects.create_user(username="forecast-alert-donor")
        donor_profile = DonorProfile.objects.create(user=donor_user, blood_group="O+")
        Hospital.objects.create(
            name="Risk Alert Center",
            registration_id="ALERT-002",
            address="Alert address",
            city="Pune",
        )

        def forecast_side_effect(_hospital, blood_group):
            return {
                "risk_level": "high" if blood_group == "O+" else "healthy",
                "current_units": 2,
                "safe_threshold": 5,
            }

        with (
            patch("inventory.tasks.forecast_inventory_risk_for_group", side_effect=forecast_side_effect),
            patch("inventory.tasks.nearby_available_donors", return_value=[donor_profile]),
        ):
            dispatch_inventory_risk_alerts.run()
            dispatch_inventory_risk_alerts.run()

        self.assertEqual(
            DonorAlert.objects.filter(
                recipient=donor_user,
                category=DonorAlert.Category.FORECAST,
            ).count(),
            1,
        )