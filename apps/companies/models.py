"""
Company models for tracking investment targets.
"""
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

from core.models import SoftDeleteModel
from core.mixins import OrganizationMixin


class CompanyQuerySet(models.QuerySet):
    """Custom queryset for Company model."""

    def for_organization(self, organization):
        return self.filter(organization=organization)

    def portfolio(self):
        return self.filter(status=Company.Status.PORTFOLIO)

    def on_deck(self):
        return self.filter(status=Company.Status.ON_DECK)

    def watchlist(self):
        return self.filter(status=Company.Status.WATCHLIST)

    def active(self):
        """Companies that are not passed or archived."""
        return self.exclude(status__in=[Company.Status.PASSED, Company.Status.ARCHIVED])

    def search(self, query):
        """Full-text search using SearchVectorField."""
        from django.contrib.postgres.search import SearchQuery
        return self.filter(search_vector=SearchQuery(query, search_type='websearch'))


class CompanyManager(models.Manager):
    """Custom manager that excludes soft-deleted companies."""

    def get_queryset(self):
        return CompanyQuerySet(self.model, using=self._db).filter(is_deleted=False)


class Company(SoftDeleteModel, OrganizationMixin):
    """
    A company being researched for potential investment.
    """
    class Status(models.TextChoices):
        PORTFOLIO = 'portfolio', 'Portfolio'
        ON_DECK = 'on_deck', 'On Deck'
        WATCHLIST = 'watchlist', 'Watchlist'
        PASSED = 'passed', 'Passed'
        ARCHIVED = 'archived', 'Archived'

    class Sector(models.TextChoices):
        TECHNOLOGY = 'technology', 'Technology'
        HEALTHCARE = 'healthcare', 'Healthcare'
        FINANCIALS = 'financials', 'Financials'
        CONSUMER_DISCRETIONARY = 'consumer_discretionary', 'Consumer Discretionary'
        CONSUMER_STAPLES = 'consumer_staples', 'Consumer Staples'
        INDUSTRIALS = 'industrials', 'Industrials'
        ENERGY = 'energy', 'Energy'
        MATERIALS = 'materials', 'Materials'
        UTILITIES = 'utilities', 'Utilities'
        REAL_ESTATE = 'real_estate', 'Real Estate'
        COMMUNICATIONS = 'communications', 'Communications'
        OTHER = 'other', 'Other'

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.WATCHLIST,
        db_index=True
    )
    sector = models.CharField(
        max_length=30,
        choices=Sector.choices,
        blank=True,
        db_index=True
    )
    country = models.CharField(max_length=100, blank=True)

    # Investment thesis
    thesis = models.TextField(
        blank=True,
        help_text='Investment thesis summary'
    )

    # Market data
    market_cap = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Market cap in USD'
    )

    # Full-text search vector
    search_vector = SearchVectorField(null=True, blank=True)

    objects = CompanyManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'companies'
        unique_together = ['organization', 'slug']
        ordering = ['name']
        indexes = [
            GinIndex(fields=['search_vector']),
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['organization', 'sector']),
            models.Index(fields=['organization', '-updated_at']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness within organization
            original_slug = self.slug
            counter = 1
            while Company.all_objects.filter(
                organization=self.organization,
                slug=self.slug
            ).exclude(pk=self.pk).exists():
                self.slug = f'{original_slug}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('companies:detail', kwargs={'slug': self.slug})

    def get_primary_ticker(self):
        """Return the primary ticker or first ticker."""
        return self.tickers.filter(is_primary=True).first() or self.tickers.first()

    @property
    def status_color(self):
        """Return CSS color class for status."""
        colors = {
            self.Status.PORTFOLIO: 'green',
            self.Status.ON_DECK: 'yellow',
            self.Status.WATCHLIST: 'blue',
            self.Status.PASSED: 'gray',
            self.Status.ARCHIVED: 'gray',
        }
        return colors.get(self.status, 'gray')


class CompanyTicker(models.Model):
    """
    Stock ticker symbols for a company.
    Supports multiple tickers (e.g., primary listing + ADR).
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='tickers'
    )
    symbol = models.CharField(max_length=20)
    exchange = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = 'company_tickers'
        unique_together = ['company', 'symbol', 'exchange']
        ordering = ['-is_primary', 'symbol']

    def __str__(self):
        if self.exchange:
            return f'{self.symbol} ({self.exchange})'
        return self.symbol

    def save(self, *args, **kwargs):
        # Ensure only one primary ticker per company
        if self.is_primary:
            CompanyTicker.objects.filter(
                company=self.company,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
