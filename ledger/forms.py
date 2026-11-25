from django import forms
from django.utils import timezone

from .models import Account, Category, Transaction

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
RECEIPT_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


class TransactionForm(forms.ModelForm):
    posted_at = forms.DateTimeField(
        label="Posting date & time",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"],
    )

    class Meta:
        model = Transaction
        fields = ["direction", "amount", "payee", "category", "account", "posted_at", "note", "receipt", "is_recurring"]
        labels = {"amount": "Amount", "note": "Internal memo / notes", "is_recurring": "Repeats every month"}
        widgets = {
            "direction": forms.RadioSelect,
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "0.00"}),
            "payee": forms.TextInput(attrs={"placeholder": "e.g. AWS Cloud Infrastructure"}),
            "note": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["category"].queryset = Category.objects.filter(user=user)
        self.fields["category"].empty_label = "Uncategorised"
        self.fields["account"].queryset = Account.objects.filter(user=user, is_active=True)
        self.fields["account"].empty_label = None
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("posted_at", timezone.localtime().replace(second=0, microsecond=0))

    def clean_receipt(self):
        receipt = self.cleaned_data.get("receipt")
        if receipt and hasattr(receipt, "size"):
            if receipt.size > MAX_RECEIPT_BYTES:
                raise forms.ValidationError("Receipts must be 5 MB or smaller.")
            suffix = "." + receipt.name.rsplit(".", 1)[-1].lower() if "." in receipt.name else ""
            if suffix not in RECEIPT_TYPES:
                raise forms.ValidationError("Upload a PDF or an image (PNG, JPG, WebP).")
        return receipt

    def clean(self):
        cleaned = super().clean()
        direction, category = cleaned.get("direction"), cleaned.get("category")
        if direction == Transaction.Direction.TRANSFER:
            cleaned["category"] = None
        elif category and category.kind != direction:
            self.add_error("category", f"“{category}” is an {category.kind} category; pick an {direction} category.")
        return cleaned

    def save(self, commit=True):
        txn = super().save(commit=False)
        txn.user = self.user
        if commit:
            txn.save()
        return txn


class TransactionFilterForm(forms.Form):
    TABS = [("all", "All"), ("expense", "Expenses"), ("income", "Income"), ("recurring", "Recurring")]

    tab = forms.ChoiceField(choices=TABS, required=False)
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": "Search payees, notes…"}))
    account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False, empty_label="All accounts")
    category = forms.ModelChoiceField(queryset=Category.objects.none(), required=False, empty_label="All categories")
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(user=user)
        self.fields["category"].queryset = Category.objects.filter(user=user)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and start > end:
            self.add_error("end", "End date must be on or after the start date.")
        return cleaned


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "kind", "last4", "opening_balance"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Chase Checking"}),
            "last4": forms.TextInput(attrs={"placeholder": "8812", "inputmode": "numeric", "maxlength": 4}),
            "opening_balance": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Account.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("You already have an account with this name.")
        return name

    def clean_last4(self):
        last4 = self.cleaned_data["last4"].strip()
        if last4 and (len(last4) != 4 or not last4.isdigit()):
            raise forms.ValidationError("Enter exactly 4 digits, or leave it blank.")
        return last4


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Category.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("You already have a category with this name.")
        return name
