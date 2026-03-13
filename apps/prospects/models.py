from django.db import models
from django.conf import settings
from core.models import TimeStampedModel, SoftDeleteModel
from core.mixins import OrganizationMixin

class Prospect(TimeStampedModel, OrganizationMixin):
    """Sales prospect data with HubSpot sync support."""
    
    class Status(models.TextChoices):
        LEAD = 'LEAD', 'New Lead'
        QUALIFIED = 'QUALIFIED', 'Qualified'
        PROPOSAL = 'PROPOSAL', 'Proposal Sent'
        NEGOTIATION = 'NEGOTIATION', 'In Negotiation'
        WON = 'WON', 'Closed Won'
        LOST = 'LOST', 'Closed Lost'

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    company_name = models.CharField(max_length=200, blank=True, default='')
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.LEAD)
    
    # HubSpot integration fields
    hubspot_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=50, blank=True, default='')

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.company_name})"

    class Meta:
        ordering = ['-created_at']
        unique_together = ['organization', 'email']

class ProspectNote(TimeStampedModel, OrganizationMixin):
    """Activity notes for a sales prospect."""
    
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='prospect_notes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    
    # HubSpot sync
    hubspot_note_id = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        return f"Note for {self.prospect} by {self.user}"

    class Meta:
        ordering = ['-created_at']
