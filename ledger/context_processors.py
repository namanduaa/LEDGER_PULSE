from django.conf import settings


def app_settings(request):
    return {"CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL}
