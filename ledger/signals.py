from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import create_starter_data


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def give_new_users_starter_data(sender, instance, created, raw=False, **kwargs):
    """Every new user (website signup or admin) starts with a cash account and common categories."""
    if created and not raw:
        create_starter_data(instance)
