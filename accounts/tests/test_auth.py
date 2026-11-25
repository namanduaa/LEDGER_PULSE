from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, Category

User = get_user_model()
PASSWORD = "Str0ng-pass-for-tests"


class SignupTests(TestCase):
    def signup(self, **overrides):
        data = {"full_name": "Naman Test", "email": "naman@example.com", "password1": PASSWORD, "password2": PASSWORD}
        data.update(overrides)
        return self.client.post(reverse("accounts:signup"), data)

    def test_signup_creates_user_logs_in_and_redirects_to_dashboard(self):
        response = self.signup()
        self.assertRedirects(response, reverse("ledger:dashboard"))
        user = User.objects.get(email="naman@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_gives_starter_account_and_categories(self):
        self.signup()
        user = User.objects.get(email="naman@example.com")
        self.assertTrue(Account.objects.filter(user=user, name="Cash").exists())
        self.assertTrue(Category.objects.filter(user=user, kind="income").exists())
        self.assertTrue(Category.objects.filter(user=user, kind="expense").exists())

    def test_email_is_stored_lowercase_and_duplicates_are_rejected_case_insensitively(self):
        self.signup(email="Naman@Example.COM")
        self.assertTrue(User.objects.filter(email="naman@example.com").exists())
        self.client.logout()
        response = self.signup(email="NAMAN@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_mismatched_passwords_are_rejected(self):
        response = self.signup(password2="something-else-123")
        self.assertContains(response, "don&#x27;t match")
        self.assertFalse(User.objects.exists())

    def test_weak_password_is_rejected(self):
        response = self.signup(password1="12345678", password2="12345678")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("person@example.com", PASSWORD, full_name="Person")

    def test_login_with_email_any_case(self):
        response = self.client.post(reverse("accounts:login"), {"username": "PERSON@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("ledger:dashboard"))

    def test_wrong_password_shows_error(self):
        response = self.client.post(reverse("accounts:login"), {"username": "person@example.com", "password": "nope"})
        self.assertContains(response, "don&#x27;t match an account")

    def test_app_pages_require_login(self):
        for name in ["ledger:dashboard", "ledger:transactions", "ledger:settings", "budgets:list"]:
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse(name)}")

    def test_logout_is_post_only_and_ends_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class AdminTests(TestCase):
    def test_admin_user_list_shows_signed_up_users_with_activity_counts(self):
        admin = User.objects.create_superuser("admin@example.com", PASSWORD, full_name="Admin")
        User.objects.create_user("customer@example.com", PASSWORD, full_name="Customer One")
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "customer@example.com")
        self.assertContains(response, "Transactions")

    def test_non_staff_cannot_open_admin(self):
        user = User.objects.create_user("customer@example.com", PASSWORD, full_name="Customer")
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
