"""
Signals for Note model.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector

from .models import Note


@receiver(post_save, sender=Note)
def update_search_vector(sender, instance, **kwargs):
    """Update search vector when note is saved."""
    # Use update() to avoid infinite recursion
    Note.all_objects.filter(pk=instance.pk).update(
        search_vector=(
            SearchVector('title', weight='A') +
            SearchVector('content', weight='B')
        )
    )
