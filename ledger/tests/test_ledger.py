from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ledger import services
from ledger.models import Account, Category, Transaction

User = get_user_model()


def at(year, month, day, hour=12):
    return timezone.make_aware(datetime.combine(date(year, month, day), time(hour)))


class LedgerTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("me@example.com", "Str0ng-pass-x", full_name="Me")
        self.account = Account.objects.get(user=self.user, name="Cash")
        self.food = Category.objects.get(user=self.user, name="Food & Dining")
        self.salary = Category.objects.get(user=self.user, name="Salary")

    def txn(self, amount, direction="expense", when=None, category=None, user=None, **extra):
        user = user or self.user
        return Transaction.objects.create(
            user=user,
            account=extra.pop("account", self.account if user == self.user else Account.objects.get(user=user, name="Cash")),
            category=category,
            direction=direction,
            amount=Decimal(amount),
            payee=extra.pop("payee", "Shop"),
            posted_at=when or timezone.now(),
            **extra,
        )


class ServiceTests(LedgerTestCase):
    def test_period_totals_and_savings_rate(self):
        self.txn("1000.00", "income", at(2026, 10, 1), self.salary)
        self.txn("250.50", "expense", at(2026, 10, 5), self.food)
        self.txn("99.00", "expense", at(2026, 9, 30), self.food)  # previous month: excluded
        self.txn("500.00", "transfer", at(2026, 10, 6))  # transfers don't count as income or spending
        p = services.Period(2026, 10)
        totals = services.period_totals(self.user, p.start, p.end)
        self.assertEqual(totals.inflow, Decimal("1000.00"))
        self.assertEqual(totals.outflow, Decimal("250.50"))
        self.assertEqual(totals.net, Decimal("749.50"))
        self.assertEqual(totals.savings_rate, Decimal("75.0"))

    def test_savings_rate_is_none_without_income(self):
        p = services.Period(2026, 10)
        self.assertIsNone(services.period_totals(self.user, p.start, p.end).savings_rate)

    def test_month_boundaries_use_local_time(self):
        # 23:30 local time on 31 Oct belongs to October, not November.
        self.txn("10.00", when=at(2026, 10, 31, 23))
        october = services.Period(2026, 10)
        november = october.next()
        self.assertEqual(services.period_totals(self.user, october.start, october.end).outflow, Decimal("10.00"))
        self.assertEqual(services.period_totals(self.user, november.start, november.end).outflow, Decimal("0.00"))

    def test_net_position_includes_opening_balances(self):
        self.account.opening_balance = Decimal("100.00")
        self.account.save()
        self.txn("50.00", "income", at(2026, 10, 2))
        self.txn("30.00", "expense", at(2026, 10, 3))
        self.assertEqual(services.net_position(self.user), Decimal("120.00"))
        self.assertEqual(services.net_position(self.user, before=at(2026, 10, 3, 0)), Decimal("150.00"))

    def test_category_spend_shares_add_up(self):
        self.txn("75.00", when=at(2026, 10, 2), category=self.food)
        self.txn("25.00", when=at(2026, 10, 3))
        rows = services.category_spend(self.user, services.Period(2026, 10))
        self.assertEqual([r["name"] for r in rows], ["Food & Dining", "Uncategorised"])
        self.assertEqual(sum(r["share"] for r in rows), Decimal("100.0"))

    def test_daily_flows_has_one_row_per_day(self):
        self.txn("40.00", when=at(2026, 2, 10))
        days = services.daily_flows(self.user, services.Period(2026, 2))
        self.assertEqual(len(days), 28)
        self.assertEqual(days[9]["outflow"], Decimal("40.00"))
        self.assertEqual(days[9]["outflow_pct"], 100)

    def test_period_parse_falls_back_to_current_month(self):
        self.assertEqual(services.Period.parse("2026-13"), services.Period.current())
        self.assertEqual(services.Period.parse("junk"), services.Period.current())
        self.assertEqual(services.Period.parse("2025-01"), services.Period(2025, 1))
        self.assertEqual(services.Period(2025, 12).next(), services.Period(2026, 1))


class ConstraintTests(LedgerTestCase):
    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            self.txn("0.00")


class TransactionViewTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.other = User.objects.create_user("other@example.com", "Str0ng-pass-y", full_name="Other")

    def post_txn(self, **overrides):
        data = {
            "direction": "expense", "amount": "42.50", "payee": "Cafe", "category": self.food.pk,
            "account": self.account.pk, "posted_at": "2026-10-24T10:30", "note": "", "is_recurring": "",
        }
        data.update(overrides)
        return self.client.post(reverse("ledger:transaction_create"), data)

    def test_create_transaction(self):
        response = self.post_txn()
        self.assertRedirects(response, reverse("ledger:transactions"))
        txn = Transaction.objects.get(user=self.user)
        self.assertEqual(txn.amount, Decimal("42.50"))
        self.assertEqual(txn.category, self.food)

    def test_cannot_use_another_users_account_or_category(self):
        other_account = Account.objects.get(user=self.other, name="Cash")
        response = self.post_txn(account=other_account.pk)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Transaction.objects.exists())

    def test_category_kind_must_match_direction(self):
        response = self.post_txn(direction="income", category=self.food.pk)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Transaction.objects.exists())

    def test_negative_amount_rejected(self):
        self.assertEqual(self.post_txn(amount="-5").status_code, 400)

    def test_list_only_shows_own_transactions(self):
        self.txn("10.00", payee="Mine")
        self.txn("20.00", payee="Theirs", user=self.other)
        response = self.client.get(reverse("ledger:transactions"))
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")

    def test_filters_and_tabs(self):
        self.txn("10.00", payee="Coffee", category=self.food)
        self.txn("900.00", "income", payee="Payroll", category=self.salary)
        response = self.client.get(reverse("ledger:transactions"), {"tab": "income"})
        self.assertContains(response, "Payroll")
        self.assertNotContains(response, "<b>Coffee</b>")
        response = self.client.get(reverse("ledger:transactions"), {"q": "coff"})
        self.assertContains(response, "<b>Coffee</b>")
        self.assertNotContains(response, "Payroll")

    def test_cannot_edit_another_users_transaction(self):
        theirs = self.txn("20.00", user=self.other)
        self.assertEqual(self.client.get(reverse("ledger:transaction_edit", args=[theirs.pk])).status_code, 404)

    def test_bulk_delete_ignores_other_users_ids(self):
        mine = self.txn("10.00")
        theirs = self.txn("20.00", user=self.other)
        self.client.post(reverse("ledger:transaction_bulk"), {"ids": [mine.pk, theirs.pk], "action": "delete"})
        self.assertFalse(Transaction.objects.filter(pk=mine.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=theirs.pk).exists())

    def test_bulk_categorize(self):
        t = self.txn("10.00")
        self.client.post(reverse("ledger:transaction_bulk"), {"ids": [t.pk], "action": "categorize", "category": self.food.pk})
        t.refresh_from_db()
        self.assertEqual(t.category, self.food)

    def test_receipt_download_is_owner_only(self):
        theirs = self.txn("20.00", user=self.other)
        self.assertEqual(self.client.get(reverse("ledger:receipt", args=[theirs.pk])).status_code, 404)

    def test_dashboard_renders_with_and_without_data(self):
        self.assertEqual(self.client.get(reverse("ledger:dashboard")).status_code, 200)
        self.txn("10.00", category=self.food)
        self.txn("100.00", "income", category=self.salary)
        response = self.client.get(reverse("ledger:dashboard"))
        self.assertContains(response, "Executive Treasury Overview")
        self.assertContains(response, "Food &amp; Dining")

    def test_settings_add_account_rejects_duplicate_name(self):
        self.client.post(reverse("ledger:settings"), {"add_account": "1", "account-name": "HDFC Savings", "account-kind": "savings", "account-last4": "1234", "account-opening_balance": "0"})
        self.assertTrue(Account.objects.filter(user=self.user, name="HDFC Savings").exists())
        response = self.client.post(reverse("ledger:settings"), {"add_account": "1", "account-name": "hdfc savings", "account-kind": "savings", "account-last4": "", "account-opening_balance": "0"})
        self.assertContains(response, "already have an account")

    def test_account_with_transactions_is_archived_not_deleted(self):
        self.txn("10.00")
        self.client.post(reverse("ledger:account_delete", args=[self.account.pk]))
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)
