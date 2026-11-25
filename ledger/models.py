from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Account(models.Model):
    """Where money sits: a bank account, a card, or cash."""

    class Kind(models.TextChoices):
        CHECKING = "checking", "Checking"
        SAVINGS = "savings", "Savings"
        CREDIT_CARD = "credit_card", "Credit card"
        CASH = "cash", "Cash"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_accounts")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.CHECKING)
    last4 = models.CharField("last 4 digits", max_length=4, blank=True)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_account_name_per_user")]

    def __str__(self):
        return f"{self.name} (••{self.last4})" if self.last4 else self.name


class Category(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.EXPENSE)
    color = models.CharField(max_length=7, default="#4f46e5", help_text="Hex colour, e.g. #4f46e5")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name_plural = "categories"
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_category_name_per_user")]

    def __str__(self):
        return self.name


class TransactionQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def expenses(self):
        return self.filter(direction=Transaction.Direction.EXPENSE)

    def income(self):
        return self.filter(direction=Transaction.Direction.INCOME)

    def between(self, start, end):
        """Half-open range: start <= posted_at < end."""
        return self.filter(posted_at__gte=start, posted_at__lt=end)


class Transaction(models.Model):
    class Direction(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        TRANSFER = "transfer", "Transfer"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SETTLED = "settled", "Settled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices, default=Direction.EXPENSE)
    # Always stored as a positive number; `direction` says which way the money moved.
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payee = models.CharField("merchant / payee", max_length=120)
    note = models.CharField("memo", max_length=255, blank=True)
    posted_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.SETTLED)
    is_recurring = models.BooleanField(default=False)
    receipt = models.FileField(upload_to="receipts/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ["-posted_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-posted_at"], name="txn_user_posted_idx"),
            models.Index(fields=["user", "direction", "posted_at"], name="txn_user_dir_posted_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="transaction_amount_positive"),
        ]

    def __str__(self):
        return f"{self.payee} {self.signed_amount}"

    @property
    def signed_amount(self):
        if self.direction == self.Direction.EXPENSE:
            return -self.amount
        if self.direction == self.Direction.INCOME:
            return self.amount
        return Decimal("0.00")
