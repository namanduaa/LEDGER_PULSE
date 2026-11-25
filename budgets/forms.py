from django import forms

from ledger.models import Category

from .models import BudgetEnvelope


class EnvelopeForm(forms.ModelForm):
    class Meta:
        model = BudgetEnvelope
        fields = ["name", "kind", "monthly_cap", "categories"]
        labels = {"monthly_cap": "Monthly cap", "categories": "Categories it covers"}
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Food & Dining"}),
            "monthly_cap": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "0.00"}),
            "categories": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["categories"].queryset = Category.objects.filter(user=user, kind=Category.Kind.EXPENSE)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = BudgetEnvelope.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have an envelope with this name.")
        return name

    def save(self, commit=True):
        envelope = super().save(commit=False)
        envelope.user = self.user
        if commit:
            envelope.save()
            self.save_m2m()
        return envelope
