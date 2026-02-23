"""
Models for event planning and RSVP tracking.
"""
import uuid

from django.db import models
from django.utils import timezone

from core.models import SoftDeleteModel
from core.mixins import OrganizationMixin


class Event(SoftDeleteModel, OrganizationMixin):
    """A dinner or event with invited guests."""

    name = models.CharField(max_length=255)
    date = models.DateTimeField()
    location = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    email_subject = models.CharField(
        max_length=255,
        blank=True,
        help_text='Subject line for invitation emails',
    )
    email_body_template = models.TextField(
        blank=True,
        help_text='Template for invitation email body. Use {guest_name}, {event_name}, {date}, {location}, {rsvp_url} as placeholders.',
    )

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.name

    @property
    def guest_count(self):
        return self.guests.count()

    @property
    def rsvp_yes_count(self):
        return self.guests.filter(rsvp_status='yes').count()

    @property
    def rsvp_no_count(self):
        return self.guests.filter(rsvp_status='no').count()

    @property
    def rsvp_pending_count(self):
        return self.guests.filter(rsvp_status='pending').count()


class GuestScreenshot(SoftDeleteModel, OrganizationMixin):
    """An uploaded screenshot containing guest names and emails."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='screenshots',
    )
    image = models.ImageField(upload_to='events/screenshots/')
    extracted_data = models.JSONField(
        default=list,
        blank=True,
        help_text='JSON array of {name, email} extracted from screenshot',
    )
    is_processed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Screenshot for {self.event.name} ({self.created_at:%Y-%m-%d})'


class Guest(SoftDeleteModel, OrganizationMixin):
    """An invited guest for an event."""

    RSVP_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('yes', 'Yes'),
        ('no', 'No'),
    ]

    FOOD_PREFERENCE_CHOICES = [
        ('no_restrictions', 'No Restrictions'),
        ('vegetarian', 'Vegetarian'),
        ('vegan', 'Vegan'),
        ('gluten_free', 'Gluten-Free'),
        ('kosher', 'Kosher'),
        ('halal', 'Halal'),
        ('other', 'Other'),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='guests',
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    rsvp_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    rsvp_status = models.CharField(
        max_length=10,
        choices=RSVP_STATUS_CHOICES,
        default='pending',
    )
    food_preference = models.CharField(
        max_length=20,
        choices=FOOD_PREFERENCE_CHOICES,
        default='no_restrictions',
    )
    dietary_notes = models.TextField(blank=True)
    generated_email = models.TextField(blank=True)
    email_sent = models.BooleanField(default=False)
    rsvp_responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ['event', 'email']

    def __str__(self):
        return f'{self.name} ({self.email})'

    def get_rsvp_url(self, request=None):
        """Get the full RSVP URL for this guest."""
        from django.urls import reverse
        path = reverse('events:rsvp_public', kwargs={'token': self.rsvp_token})
        if request:
            return request.build_absolute_uri(path)
        return path
