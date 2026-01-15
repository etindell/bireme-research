"""
Models for the news aggregation feature.
"""
import hashlib

from django.db import models


class CompanyNews(models.Model):
    """News item for a company, fetched and processed by AI."""

    class Importance(models.TextChoices):
        HIGH = 'high', 'High'
        MEDIUM = 'medium', 'Medium'
        LOW = 'low', 'Low'

    class SourceType(models.TextChoices):
        WEB = 'web', 'Web Search'
        SEC_EDGAR = 'sec_edgar', 'SEC EDGAR'

    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='news_items'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='news_items'
    )

    # Content
    headline = models.CharField(max_length=500)
    summary = models.TextField(help_text='AI-generated summary')
    source_url = models.URLField(max_length=2000)
    source_name = models.CharField(max_length=100)  # "Reuters", "SEC EDGAR", etc.
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.WEB
    )

    # AI Classification
    importance = models.CharField(
        max_length=10,
        choices=Importance.choices,
        default=Importance.MEDIUM
    )
    event_type = models.CharField(
        max_length=50,
        blank=True,
        help_text='Event category: earnings, management, M&A, regulatory, product, legal, analyst, other'
    )

    # Timestamps
    published_at = models.DateTimeField(help_text='When the article was published')
    fetched_at = models.DateTimeField(auto_now_add=True)

    # User interaction
    is_read = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)

    # Deduplication
    url_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['company', '-published_at']),
            models.Index(fields=['organization', '-published_at']),
            models.Index(fields=['importance', '-published_at']),
        ]
        unique_together = ['company', 'url_hash']
        verbose_name = 'Company News'
        verbose_name_plural = 'Company News'

    def __str__(self):
        return f"{self.company.name}: {self.headline[:50]}"

    def save(self, *args, **kwargs):
        if not self.url_hash:
            self.url_hash = hashlib.sha256(self.source_url.encode()).hexdigest()
        if not self.organization_id and self.company_id:
            self.organization = self.company.organization
        super().save(*args, **kwargs)

    @property
    def importance_color(self):
        """Return Tailwind color class for importance badge."""
        colors = {
            self.Importance.HIGH: 'red',
            self.Importance.MEDIUM: 'yellow',
            self.Importance.LOW: 'gray',
        }
        return colors.get(self.importance, 'gray')
