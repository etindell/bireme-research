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
    business_summary = models.TextField(
        blank=True,
        help_text='Business description from Yahoo Finance'
    )

    # Watchlist alert price
    alert_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Price at which to consider deeper research'
    )
    alert_price_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text='Brief explanation of why this alert price was chosen'
    )
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Current stock price (auto-fetched)'
    )
    ev_ebitda = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Enterprise Value / EBITDA ratio'
    )
    price_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When price was last fetched'
    )

    # Full-text search vector
    search_vector = SearchVectorField(null=True, blank=True)

    # AI-generated summary
    ai_summary = models.TextField(
        blank=True,
        help_text='AI-generated summary of research notes'
    )
    summary_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the AI summary was last generated'
    )

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

    def get_active_valuation(self):
        """Return the active valuation for this company."""
        return self.valuations.filter(is_active=True, is_deleted=False).first()

    @property
    def irr(self):
        """Return IRR from active valuation."""
        valuation = self.get_active_valuation()
        return valuation.calculated_irr if valuation else None

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

    @property
    def is_alert_triggered(self):
        """Check if current price is at or below alert price."""
        if self.alert_price and self.current_price:
            return self.current_price <= self.alert_price
        return False

    @property
    def alert_discount_percent(self):
        """Return percentage below alert price (positive = below alert)."""
        if self.alert_price and self.current_price and self.alert_price > 0:
            return ((self.alert_price - self.current_price) / self.alert_price) * 100
        return None


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


class ValuationHistory(models.Model):
    """
    Historical record of valuation forecast changes.
    Created automatically when FCF or terminal value forecasts are modified.
    """
    valuation = models.ForeignKey(
        'CompanyValuation',
        on_delete=models.CASCADE,
        related_name='history'
    )

    # Snapshot of forecast values at time of change
    fcf_year_1 = models.DecimalField(max_digits=12, decimal_places=2)
    fcf_year_2 = models.DecimalField(max_digits=12, decimal_places=2)
    fcf_year_3 = models.DecimalField(max_digits=12, decimal_places=2)
    fcf_year_4 = models.DecimalField(max_digits=12, decimal_places=2)
    fcf_year_5 = models.DecimalField(max_digits=12, decimal_places=2)
    terminal_value = models.DecimalField(max_digits=12, decimal_places=2)
    shares_outstanding = models.DecimalField(max_digits=20, decimal_places=2)

    # Price and IRR at time of snapshot
    current_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    calculated_irr = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    note = models.CharField(max_length=255, blank=True, help_text='Optional note about this change')

    class Meta:
        db_table = 'valuation_history'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.valuation.company.name} history ({self.created_at.strftime("%Y-%m-%d %H:%M")})'


class CompanyValuation(SoftDeleteModel):
    """
    Valuation data for IRR calculation including FCF forecasts and terminal value.
    One active valuation per company at a time.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='valuations'
    )

    # Share data
    shares_outstanding = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Shares outstanding (in millions)'
    )

    # FCF Per Share Forecasts (Years 1-5)
    fcf_year_1 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='FCF per share forecast - Year 1'
    )
    fcf_year_2 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='FCF per share forecast - Year 2'
    )
    fcf_year_3 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='FCF per share forecast - Year 3'
    )
    fcf_year_4 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='FCF per share forecast - Year 4'
    )
    fcf_year_5 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='FCF per share forecast - Year 5'
    )

    # Terminal Value
    terminal_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Terminal value per share at end of Year 5'
    )

    # Stock Price - can be auto-fetched or manually overridden
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Current stock price (auto-fetched from Yahoo Finance)'
    )
    price_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Manual price override (takes precedence over fetched price)'
    )
    price_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When price was last fetched'
    )

    # Computed IRR (cached for performance)
    calculated_irr = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Calculated IRR as decimal (e.g., 0.15 = 15%)'
    )
    irr_last_calculated = models.DateTimeField(null=True, blank=True)

    # Valuation metadata
    as_of_date = models.DateField(help_text='Date these estimates are based on')
    notes = models.TextField(blank=True, help_text='Notes about valuation assumptions')
    is_active = models.BooleanField(
        default=True,
        help_text='Only one active valuation per company'
    )

    class Meta:
        db_table = 'company_valuations'
        ordering = ['-as_of_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['-calculated_irr']),
        ]

    def __str__(self):
        return f'{self.company.name} valuation ({self.as_of_date})'

    @property
    def effective_price(self):
        """Return the price to use for calculations (override or fetched)."""
        return self.price_override or self.current_price

    def get_cash_flows(self):
        """Return list of cash flows for IRR calculation."""
        price = self.effective_price
        if not price:
            return None
        return [
            -float(price),  # Year 0: negative (investment)
            float(self.fcf_year_1),
            float(self.fcf_year_2),
            float(self.fcf_year_3),
            float(self.fcf_year_4),
            float(self.fcf_year_5) + float(self.terminal_value),  # Year 5 includes terminal value
        ]

    def calculate_irr(self):
        """Calculate and cache IRR."""
        from django.utils import timezone
        cash_flows = self.get_cash_flows()
        if cash_flows:
            from apps.companies.services import calculate_irr
            self.calculated_irr = calculate_irr(cash_flows)
            self.irr_last_calculated = timezone.now()
            return self.calculated_irr
        return None

    def _get_forecast_fields(self):
        """Return a dict of forecast-related fields for comparison."""
        return {
            'fcf_year_1': self.fcf_year_1,
            'fcf_year_2': self.fcf_year_2,
            'fcf_year_3': self.fcf_year_3,
            'fcf_year_4': self.fcf_year_4,
            'fcf_year_5': self.fcf_year_5,
            'terminal_value': self.terminal_value,
            'shares_outstanding': self.shares_outstanding,
        }

    def _create_history_snapshot(self, user=None):
        """Create a history record with current forecast values."""
        ValuationHistory.objects.create(
            valuation=self,
            fcf_year_1=self.fcf_year_1,
            fcf_year_2=self.fcf_year_2,
            fcf_year_3=self.fcf_year_3,
            fcf_year_4=self.fcf_year_4,
            fcf_year_5=self.fcf_year_5,
            terminal_value=self.terminal_value,
            shares_outstanding=self.shares_outstanding,
            current_price=self.effective_price,
            calculated_irr=self.calculated_irr,
            created_by=user,
        )

    def save(self, *args, **kwargs):
        # Extract custom kwargs
        track_history = kwargs.pop('track_history', True)
        history_user = kwargs.pop('history_user', None)

        # Check if this is an update with forecast changes
        should_record_history = False
        if self.pk and track_history:
            try:
                old_valuation = CompanyValuation.objects.get(pk=self.pk)
                old_fields = {
                    'fcf_year_1': old_valuation.fcf_year_1,
                    'fcf_year_2': old_valuation.fcf_year_2,
                    'fcf_year_3': old_valuation.fcf_year_3,
                    'fcf_year_4': old_valuation.fcf_year_4,
                    'fcf_year_5': old_valuation.fcf_year_5,
                    'terminal_value': old_valuation.terminal_value,
                    'shares_outstanding': old_valuation.shares_outstanding,
                }
                new_fields = self._get_forecast_fields()
                # Check if any forecast field changed
                if old_fields != new_fields:
                    should_record_history = True
            except CompanyValuation.DoesNotExist:
                pass

        # Ensure only one active valuation per company
        if self.is_active and self.company_id:
            CompanyValuation.objects.filter(
                company=self.company,
                is_active=True
            ).exclude(pk=self.pk).update(is_active=False)

        # Recalculate IRR on save if we have a price
        if self.effective_price:
            self.calculate_irr()

        super().save(*args, **kwargs)

        # Record history after save (so we have the pk for new records)
        if should_record_history:
            self._create_history_snapshot(user=history_user)
