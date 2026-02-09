"""
Models for pomodoro timer tracking.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel
from core.mixins import OrganizationMixin, OrganizationQuerySetMixin


class PomodoroQuerySet(OrganizationQuerySetMixin, models.QuerySet):
    """Custom QuerySet for Pomodoro model."""

    def for_user(self, user):
        return self.filter(user=user)

    def completed(self):
        return self.filter(is_completed=True)

    def today(self):
        now = timezone.now()
        return self.filter(started_at__date=now.date())

    def for_week(self, week_offset=0):
        """Get pomodoros for a given week. week_offset=0 is current week."""
        now = timezone.now()
        # Monday of current week
        monday = (now - timezone.timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Apply offset
        monday = monday - timezone.timedelta(weeks=-week_offset)
        sunday = monday + timezone.timedelta(days=7)
        return self.filter(started_at__gte=monday, started_at__lt=sunday)


class Pomodoro(TimeStampedModel, OrganizationMixin):
    """A single pomodoro work cycle."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pomodoros'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pomodoros'
    )
    topic_label = models.CharField(
        max_length=255,
        help_text='Denormalized display label for the topic'
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    was_focused = models.BooleanField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=20)

    objects = PomodoroQuerySet.as_manager()

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.topic_label} - {self.started_at:%Y-%m-%d %H:%M}'

    def mark_complete(self):
        """Mark this pomodoro as completed."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_completed', 'completed_at'])

    def set_focus_response(self, was_focused):
        """Record whether user stayed focused."""
        self.was_focused = was_focused
        self.save(update_fields=['was_focused'])

    @property
    def end_time(self):
        """When the timer should end (for client-side countdown)."""
        return self.started_at + timezone.timedelta(minutes=self.duration_minutes)

    @property
    def seconds_remaining(self):
        """Seconds remaining on the timer. Returns 0 if elapsed."""
        remaining = (self.end_time - timezone.now()).total_seconds()
        return max(0, int(remaining))
