from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from donors.models import DonorDevice
from .models import DonorAlert
from .tasks import dispatch_pending_firebase_alerts
from .models import Reward


class RewardTest(TestCase):
    def test_reward_is_non_cash_by_design(self):
        reward = Reward.objects.create(
            title="Free health checkup",
            description="A basic post-donation health checkup.",
            reward_type=Reward.RewardType.HEALTH_CHECKUP,
        )
        self.assertNotIn("cash", reward.get_reward_type_display().lower())


class FirebasePushTaskTest(TestCase):
    @override_settings(FIREBASE_ENABLED=True)
    @patch("rewards.tasks.send_push_message")
    def test_pending_alert_is_sent_to_donor_devices(self, send_push_message):
        user = get_user_model().objects.create_user(username="push-task-donor")
        DonorDevice.objects.create(user=user, fcm_token="push-task-token")
        alert = DonorAlert.objects.create(
            recipient=user,
            category=DonorAlert.Category.SHORTAGE,
            message="A nearby center needs O+ donors.",
            dedupe_key="push-task-alert",
        )

        sent_count = dispatch_pending_firebase_alerts.run()

        self.assertEqual(sent_count, 1)
        send_push_message.assert_called_once_with(
            token="push-task-token",
            title="SetuX donor alert",
            body="A nearby center needs O+ donors.",
        )
        alert.refresh_from_db()
        self.assertFalse(alert.push_pending)
        self.assertIsNotNone(alert.push_sent_at)

    @override_settings(FIREBASE_ENABLED=False)
    @patch("rewards.tasks.send_push_message")
    def test_firebase_push_stays_disabled_without_explicit_configuration(self, send_push_message):
        self.assertEqual(dispatch_pending_firebase_alerts.run(), 0)
        send_push_message.assert_not_called()