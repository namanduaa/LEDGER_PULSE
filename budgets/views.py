from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ledger.services import Period

from .forms import EnvelopeForm
from .models import BudgetEnvelope
from .services import budget_summary, envelope_statuses


@login_required
def budget_list(request):
    period = Period.parse(request.GET.get("month"))
    form = EnvelopeForm(request.POST or None, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            envelope = form.save()
            messages.success(request, f"Created envelope {envelope.name}.")
            return redirect("budgets:list")
        messages.error(request, "The envelope wasn't created. Check the form.")

    statuses = envelope_statuses(request.user, period)
    context = {
        "period": period,
        "statuses": statuses,
        "summary": budget_summary(statuses),
        "days_elapsed": period.days_elapsed(),
        "elapsed_pct": round(period.days_elapsed() / period.days_in_month * 100, 1),
        "form": form,
    }
    return render(request, "budgets/list.html", context, status=400 if form.errors else 200)


@login_required
def envelope_edit(request, pk):
    envelope = get_object_or_404(BudgetEnvelope, pk=pk, user=request.user)
    form = EnvelopeForm(request.POST or None, instance=envelope, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Updated {envelope.name}.")
        return redirect("budgets:list")
    return render(request, "budgets/edit.html", {"form": form, "envelope": envelope})


@login_required
@require_POST
def envelope_delete(request, pk):
    envelope = get_object_or_404(BudgetEnvelope, pk=pk, user=request.user)
    envelope.delete()
    messages.success(request, f"Deleted envelope {envelope.name}.")
    return redirect("budgets:list")
