"""
Abstract base models for Bireme Research platform.

These models provide common functionality like timestamps, soft deletes,
and audit trails that are inherited by all major models.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """
    Manager that excludes soft-deleted objects by default.
    Use this as the default manager for models with soft delete.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """
    Manager that includes all objects, including soft-deleted ones.
    Use this when you need to access deleted records.
    """
    pass


class TimeStampedModel(models.Model):
    """
    Abstract base model with audit trail fields.

    Provides:
    - created_at: When the record was created
    - updated_at: When the record was last modified
    - created_by: User who created the record
    - updated_by: User who last modified the record
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_created'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_updated'
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Auto-set updated_by if user is provided
        user = kwargs.pop('user', None)
        if user:
            if not self.pk:
                self.created_by = user
            self.updated_by = user
        super().save(*args, **kwargs)


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract base model with soft delete capability.

    Instead of hard deleting records, this model sets is_deleted=True
    and records when and who deleted the record.

    The default manager (objects) excludes deleted records.
    Use all_objects to include deleted records.
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_deleted'
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False, user=None):
        """
        Soft delete by default. Pass hard=True for actual deletion.

        Args:
            hard: If True, permanently delete the record
            user: User performing the deletion (for audit trail)
        """
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def restore(self, user=None):
        """
        Restore a soft-deleted record.

        Args:
            user: User performing the restoration
        """
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        if user:
            self.updated_by = user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_by'])
