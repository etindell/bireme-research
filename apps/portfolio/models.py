from django.db import models

from core.mixins import OrganizationMixin
from core.models import SoftDeleteModel


class PortfolioSnapshot(SoftDeleteModel, OrganizationMixin):
    """A point-in-time portfolio snapshot extracted from an uploaded file."""
    name = models.CharField(max_length=255, blank=True)
    as_of_date = models.DateField()
    source_file = models.FileField(upload_to='portfolio_snapshots/')
    extraction_raw = models.JSONField(blank=True, null=True)
    notes = models.TextField(blank=True)

    # Portfolio-level computed fields (cached)
    total_irr = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    total_volatility = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ['-as_of_date', '-created_at']

    def __str__(self):
        return self.name or f'Portfolio {self.as_of_date}'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('portfolio:detail', kwargs={'pk': self.pk})


class PortfolioPosition(models.Model):
    """A single position within a snapshot."""
    snapshot = models.ForeignKey(PortfolioSnapshot, on_delete=models.CASCADE, related_name='positions')
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True)
    ticker = models.CharField(max_length=20)
    name_extracted = models.CharField(max_length=255, blank=True)

    # Weights
    current_weight = models.DecimalField(max_digits=6, decimal_places=4)
    proposed_weight = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)

    # IRR
    irr = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    irr_source = models.CharField(max_length=20, choices=[
        ('valuation', 'From Valuation Model'),
        ('manual', 'Manual Entry'),
    ], default='valuation')

    class Meta:
        ordering = ['-current_weight']

    def __str__(self):
        return f'{self.ticker} ({self.current_weight:.2%})'

    @property
    def effective_weight(self):
        return self.proposed_weight if self.proposed_weight is not None else self.current_weight
