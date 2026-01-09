"""
Todo models for task tracking in Bireme Research platform.

Supports:
- Automatic quarterly update todos for Portfolio and Watchlist companies
- Manual custom todos per company
- Investor letter review todos with embedded notes
- Quick watchlist additions from investor letter reviews
"""
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.models import SoftDeleteModel
from core.mixins import OrganizationMixin


class TodoCategory(models.Model):
    """
    Categories for todos: Maintenance (existing portfolio) vs Research (new ideas).
    Seeded per organization.
    """
    class CategoryType(models.TextChoices):
        MAINTENANCE = 'maintenance', 'Maintenance'
        RESEARCH = 'research', 'Research'

    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='todo_categories'
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    category_type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        default=CategoryType.RESEARCH
    )
    color = models.CharField(max_length=7, default='#6B7280')
    icon = models.CharField(max_length=50, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'todo_categories'
        unique_together = ['organization', 'slug']
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class TodoQuerySet(models.QuerySet):
    """Custom queryset for Todo model."""

    def for_organization(self, organization):
        return self.filter(organization=organization)

    def for_company(self, company):
        return self.filter(company=company)

    def pending(self):
        return self.filter(is_completed=False)

    def completed(self):
        return self.filter(is_completed=True)

    def maintenance(self):
        return self.filter(category__category_type=TodoCategory.CategoryType.MAINTENANCE)

    def research(self):
        return self.filter(category__category_type=TodoCategory.CategoryType.RESEARCH)

    def auto_generated(self):
        return self.filter(is_auto_generated=True)

    def manual(self):
        return self.filter(is_auto_generated=False)


class TodoManager(models.Manager):
    """Custom manager that excludes soft-deleted todos."""

    def get_queryset(self):
        return TodoQuerySet(self.model, using=self._db).filter(is_deleted=False)


class Todo(SoftDeleteModel, OrganizationMixin):
    """
    A task/todo item for research workflow.

    Todos can be:
    - Auto-generated (quarterly updates, investor letter reviews)
    - Manual (custom user-created todos)

    Categorized as:
    - Maintenance: For existing portfolio companies
    - Research: For new ideas and watchlist companies
    """
    class TodoType(models.TextChoices):
        QUARTERLY_UPDATE = 'quarterly_update', 'Quarterly Update'
        INVESTOR_LETTER = 'investor_letter', 'Investor Letter Review'
        CUSTOM = 'custom', 'Custom'

    # Core fields
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    # Associated company (optional - investor letter todos may not have one)
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='todos'
    )

    # Categorization
    category = models.ForeignKey(
        TodoCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='todos'
    )
    todo_type = models.CharField(
        max_length=30,
        choices=TodoType.choices,
        default=TodoType.CUSTOM,
        db_index=True
    )

    # Completion tracking
    is_completed = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_todos'
    )

    # Auto-generation metadata
    is_auto_generated = models.BooleanField(default=False)
    quarter = models.CharField(
        max_length=7,
        blank=True,
        help_text='Quarter this todo relates to (e.g., 2024-Q1)'
    )
    fiscal_year = models.PositiveIntegerField(null=True, blank=True)

    # For investor letter todos - embedded notes
    investor_letter_notes = models.TextField(
        blank=True,
        help_text='Notes about investor letters read this quarter'
    )

    objects = TodoManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'todos'
        ordering = ['is_completed', '-created_at']
        indexes = [
            models.Index(fields=['organization', 'is_completed']),
            models.Index(fields=['organization', 'company']),
            models.Index(fields=['organization', 'todo_type']),
            models.Index(fields=['organization', 'quarter']),
            models.Index(fields=['company', 'is_completed']),
        ]

    def __str__(self):
        return self.title[:50]

    def get_absolute_url(self):
        return reverse('todos:detail', kwargs={'pk': self.pk})

    def mark_complete(self, user=None):
        """Mark this todo as completed."""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.completed_by = user
        self.save(update_fields=['is_completed', 'completed_at', 'completed_by', 'updated_at'])

    def mark_incomplete(self):
        """Mark this todo as incomplete."""
        self.is_completed = False
        self.completed_at = None
        self.completed_by = None
        self.save(update_fields=['is_completed', 'completed_at', 'completed_by', 'updated_at'])

    @property
    def category_color(self):
        """Return the category color or a default."""
        if self.category:
            return self.category.color
        return '#6B7280'

    @property
    def is_investor_letter(self):
        """Check if this is an investor letter todo."""
        return self.todo_type == self.TodoType.INVESTOR_LETTER


class WatchlistQuickAdd(models.Model):
    """
    Companies to add to watchlist from investor letter review.
    Associated with an investor letter todo.

    Allows quick capture of 5-10 companies with minimal info.
    """
    todo = models.ForeignKey(
        Todo,
        on_delete=models.CASCADE,
        related_name='watchlist_additions'
    )
    ticker = models.CharField(max_length=20)
    alert_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    note = models.CharField(
        max_length=500,
        blank=True,
        help_text='Brief note about why this company is interesting'
    )
    is_processed = models.BooleanField(
        default=False,
        help_text='Whether this has been converted to a Company'
    )
    created_company = models.ForeignKey(
        'companies.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_quick_add',
        help_text='The Company created from this quick add'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'watchlist_quick_adds'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.ticker} - {self.note[:30] if self.note else 'No note'}"
