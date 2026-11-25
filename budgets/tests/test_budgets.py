from datetime import date, datetime, time
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from budgets.models import BudgetEnvelope
from budgets.services import budget_summary, envelope_statuses
from ledger.models import Account, Category, Transaction
from ledger.services import Period

User = get_user_model()


class EnvelopeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("me@example.com", "Str0ng-pass-x", full_name="Me")
        self.account = Account.objects.get(user=self.user, name="Cash")
        self.food = Category.objects.get(user=self.user, name="Food & Dining")
        self.groceries = Category.objects.get(user=self.user, name="Groceries")
        self.envelope = BudgetEnvelope.objects.create(user=self.user, name="Food", monthly_cap=Decimal("1000.00"))
        self.envelope.categories.set([self.food, self.groceries])

    def spend(self, amount, category, day=10):
        Transaction.objects.create(
            user=self.user, account=self.account, category=category, direction="expense", amount=Decimal(amount),
            payee="Shop", posted_at=timezone.make_aware(datetime.combine(date(2026, 10, day), time(12))),
        )

    def status(self, today=date(2026, 10, 16)):
        with mock.patch("django.utils.timezone.localdate", return_value=today):
            return envelope_statuses(self.user, Period(2026, 10))[0]

    def test_spend_counts_all_linked_categories_only(self):
        self.spend("300.00", self.food)
        self.spend("200.00", self.groceries)
        self.spend("999.00", None)  # uncategorised, not in the envelope
        s = self.status()
        self.assertEqual(s.spent, Decimal("500.00"))
        self.assertEqual(s.remaining, Decimal("500.00"))
        self.assertEqual(s.status, "safe")

    def test_status_thresholds(self):
        self.spend("850.00", self.food)
        self.assertEqual(self.status().status, "caution")
        self.spend("200.00", self.food)
        s = self.status()
        self.assertEqual(s.status, "overspent")
        self.assertEqual(s.bar_width, Decimal("100"))
        self.assertEqual(s.remaining, Decimal("-50.00"))

    def test_pace_compares_with_share_of_month_elapsed(self):
        # Oct has 31 days; on day 16 the "expected" spend is 16/31 of the cap.
        self.spend("600.00", self.food)
        s = self.status(today=date(2026, 10, 16))
        self.assertEqual(s.expected_by_now, Decimal("516.13"))
        self.assertTrue(s.is_ahead_of_pace)

    def test_summary(self):
        self.spend("250.00", self.food)
        summary = budget_summary([self.status()])
        self.assertEqual(summary["allocated"], Decimal("1000.00"))
        self.assertEqual(summary["utilization"], Decimal("25.0"))

    def test_create_envelope_page_only_offers_own_expense_categories(self):
        other = User.objects.create_user("other@example.com", "Str0ng-pass-y", full_name="Other")
        other_food = Category.objects.get(user=other, name="Food & Dining")
        self.client.force_login(self.user)
        response = self.client.post(reverse("budgets:list"), {
            "name": "Sneaky", "kind": "variable", "monthly_cap": "100", "categories": [other_food.pk],
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BudgetEnvelope.objects.filter(name="Sneaky").exists())

        response = self.client.post(reverse("budgets:list"), {
            "name": "Transport", "kind": "variable", "monthly_cap": "150",
            "categories": [Category.objects.get(user=self.user, name="Transport & Travel").pk],
        })
        self.assertRedirects(response, reverse("budgets:list"))
        self.assertTrue(BudgetEnvelope.objects.filter(user=self.user, name="Transport").exists())

    def test_budget_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("budgets:list"), {"month": "2026-10"})
        self.assertContains(response, "Budget Planning")
        self.assertContains(response, "Food")
