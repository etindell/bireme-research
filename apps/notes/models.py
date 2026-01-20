"""
Note models for research documentation.
"""
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

from core.models import SoftDeleteModel
from core.mixins import OrganizationMixin


class NoteType(models.Model):
    """
    Types/categories for notes (e.g., Earnings Call, Management Meeting).
    Configurable per organization.
    """
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='note_types'
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    color = models.CharField(max_length=7, default='#6B7280')  # Hex color
    icon = models.CharField(max_length=50, blank=True)  # Icon class name
    is_default = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'note_types'
        unique_together = ['organization', 'slug']
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class NoteQuerySet(models.QuerySet):
    """Custom queryset for Note model."""

    def for_organization(self, organization):
        return self.filter(organization=organization)

    def for_company(self, company):
        """Notes where company is primary or referenced."""
        return self.filter(
            models.Q(company=company) |
            models.Q(referenced_companies=company)
        ).distinct()

    def root_notes(self):
        """Only top-level notes (no parent)."""
        return self.filter(parent__isnull=True)

    def search(self, query):
        """Full-text search using SearchVectorField."""
        from django.contrib.postgres.search import SearchQuery
        return self.filter(search_vector=SearchQuery(query, search_type='websearch'))


class NoteManager(models.Manager):
    """Custom manager that excludes soft-deleted notes."""

    def get_queryset(self):
        return NoteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class Note(SoftDeleteModel, OrganizationMixin):
    """
    A research note with hierarchical structure.

    Notes display as collapsible bullet points:
    - `title`: The bullet point text (always visible)
    - `content`: Expanded content (shown when clicked)
    """
    # Primary company this note is about
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='notes'
    )

    # Cross-references to other companies
    referenced_companies = models.ManyToManyField(
        'companies.Company',
        related_name='referenced_in_notes',
        blank=True,
        help_text='Other companies mentioned in this note'
    )

    # Note type/category
    note_type = models.ForeignKey(
        NoteType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notes'
    )

    # Hierarchical structure (for nested bullet points)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    order = models.PositiveIntegerField(default=0)

    # Content
    title = models.CharField(
        max_length=500,
        help_text='The bullet point text (always visible)'
    )
    content = models.TextField(
        blank=True,
        help_text='Expanded content (shown when clicked)'
    )

    # State
    is_collapsed = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    is_imported = models.BooleanField(
        default=False,
        help_text='Whether this note was imported from external source'
    )

    # Date of the event being documented
    note_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date of the event (e.g., earnings call date)'
    )

    # For backdating notes imported from other apps
    written_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the note was originally written (for imported notes)'
    )

    # Full-text search vector
    search_vector = SearchVectorField(null=True, blank=True)

    objects = NoteManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'notes'
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            GinIndex(fields=['search_vector']),
            models.Index(fields=['organization', 'company']),
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['parent', 'order']),
        ]

    def __str__(self):
        return self.title[:50]

    def get_absolute_url(self):
        return reverse('notes:detail', kwargs={'pk': self.pk})

    def get_children(self):
        """Get direct children ordered by order field."""
        return self.children.filter(is_deleted=False).order_by('order')

    def get_descendants(self):
        """Get all descendant notes recursively."""
        descendants = []
        for child in self.get_children():
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants

    def get_ancestors(self):
        """Get all ancestor notes (from root to direct parent)."""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors[::-1]  # Reverse to get root first

    @property
    def depth(self):
        """Calculate depth in the tree (0 = root)."""
        return len(self.get_ancestors())

    @property
    def is_root(self):
        """Whether this is a top-level note."""
        return self.parent is None

    @property
    def display_date(self):
        """Return written_at if set, otherwise created_at."""
        return self.written_at or self.created_at

    def get_all_companies(self):
        """Return primary company plus all referenced companies."""
        companies = [self.company]
        companies.extend(self.referenced_companies.all())
        return companies


def note_image_path(instance, filename):
    """Generate upload path for note images."""
    import uuid
    ext = filename.split('.')[-1] if '.' in filename else 'png'
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    return f"note_images/{instance.organization.slug}/{new_filename}"


class NoteImage(models.Model):
    """
    Uploaded images for notes.
    Images can be pasted directly into the note editor.
    """
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='note_images'
    )
    note = models.ForeignKey(
        Note,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='images',
        help_text='Associated note (can be null for newly pasted images)'
    )
    image = models.ImageField(upload_to=note_image_path)
    uploaded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_note_images'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional metadata
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)  # in bytes

    class Meta:
        db_table = 'note_images'
        ordering = ['-created_at']

    def __str__(self):
        return f"Image {self.pk} - {self.original_filename or 'pasted'}"

    @property
    def url(self):
        return self.image.url if self.image else ''

    @property
    def markdown(self):
        """Return markdown syntax for embedding this image."""
        return f"![{self.original_filename or 'image'}]({self.url})"


class NoteCashFlow(models.Model):
    """
    Cash flow assumptions attached to a note.
    Stores a snapshot of IRR calculation data at the time of note creation.
    """
    note = models.OneToOneField(
        Note,
        on_delete=models.CASCADE,
        related_name='cash_flow'
    )

    # Cash flow assumptions (snapshot at time of note)
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Stock price used for calculation'
    )
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
    terminal_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Terminal value per share at end of Year 5'
    )

    # Revenue forecasts (per share) - optional
    revenue_year_1 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Revenue per share forecast - Year 1'
    )
    revenue_year_2 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Revenue per share forecast - Year 2'
    )
    revenue_year_3 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Revenue per share forecast - Year 3'
    )
    revenue_year_4 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Revenue per share forecast - Year 4'
    )
    revenue_year_5 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Revenue per share forecast - Year 5'
    )

    # EBIT/EBITDA forecasts (per share) - which metric depends on company preference
    ebit_ebitda_year_1 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='EBIT or EBITDA per share forecast - Year 1'
    )
    ebit_ebitda_year_2 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='EBIT or EBITDA per share forecast - Year 2'
    )
    ebit_ebitda_year_3 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='EBIT or EBITDA per share forecast - Year 3'
    )
    ebit_ebitda_year_4 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='EBIT or EBITDA per share forecast - Year 4'
    )
    ebit_ebitda_year_5 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='EBIT or EBITDA per share forecast - Year 5'
    )

    # Calculated IRR at time of creation
    calculated_irr = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Calculated IRR as decimal (e.g., 0.15 = 15%)'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'note_cash_flows'

    def __str__(self):
        return f'Cash flows for note {self.note_id}'

    def get_cash_flows(self):
        """Return list of cash flows for IRR calculation."""
        return [
            -float(self.current_price),
            float(self.fcf_year_1),
            float(self.fcf_year_2),
            float(self.fcf_year_3),
            float(self.fcf_year_4),
            float(self.fcf_year_5) + float(self.terminal_value),
        ]

    def calculate_irr(self):
        """Calculate IRR from cash flows."""
        from apps.companies.services import calculate_irr
        cash_flows = self.get_cash_flows()
        return calculate_irr(cash_flows)


class NoteShareLink(models.Model):
    """
    Share link for making a note publicly accessible.
    Allows sharing individual notes via unique tokens.
    """
    note = models.ForeignKey(
        Note,
        on_delete=models.CASCADE,
        related_name='share_links'
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    allow_comments = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_share_links'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'note_share_links'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['note', 'is_active']),
        ]

    def __str__(self):
        return f"Share link for {self.note.title[:30]}"

    @classmethod
    def generate_token(cls):
        """Generate a secure random token."""
        import secrets
        return secrets.token_urlsafe(32)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('share:view', kwargs={'token': self.token})

    @property
    def is_expired(self):
        """Check if the share link has expired."""
        from django.utils import timezone
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        """Check if the share link is valid (active and not expired)."""
        return self.is_active and not self.is_expired

    def record_view(self):
        """Record a view of this shared note."""
        from django.utils import timezone
        self.view_count += 1
        self.last_viewed_at = timezone.now()
        self.save(update_fields=['view_count', 'last_viewed_at'])


class NoteShareComment(models.Model):
    """
    Comment left on a shared note by a visitor.
    Does not require authentication.
    """
    share_link = models.ForeignKey(
        NoteShareLink,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author_name = models.CharField(max_length=100, blank=True)
    author_email = models.EmailField(blank=True)
    content = models.TextField(max_length=2000)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        db_table = 'note_share_comments'
        ordering = ['created_at']

    def __str__(self):
        name = self.author_name or 'Anonymous'
        return f"Comment by {name} on {self.share_link}"
