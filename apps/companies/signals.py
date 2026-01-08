"""
Signals for Company model.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector

from .models import Company


@receiver(post_save, sender=Company)
def update_search_vector(sender, instance, **kwargs):
    """Update search vector when company is saved."""
    # Use update() to avoid infinite recursion
    Company.all_objects.filter(pk=instance.pk).update(
        search_vector=(
            SearchVector('name', weight='A') +
            SearchVector('description', weight='B') +
            SearchVector('thesis', weight='B') +
            SearchVector('sector', weight='C') +
            SearchVector('country', weight='C')
        )
    )
