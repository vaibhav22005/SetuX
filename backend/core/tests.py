from django.test import SimpleTestCase


class FoundationTest(SimpleTestCase):
    def test_project_is_configured(self):
        self.assertEqual(self.client.get("/admin/login/").status_code, 200)