from django.db import models
from django.conf import settings
from django.utils import timezone

from core.models import TimeStampedModel, SoftDeleteModel
from core.mixins import OrganizationMixin


class ComplianceSettings(TimeStampedModel, OrganizationMixin):
    """Firm-level compliance configuration."""

    firm_name = models.CharField(max_length=255, default='Bireme Capital')
    fiscal_year_end_month = models.PositiveSmallIntegerField(default=12)
    fiscal_year_end_day = models.PositiveSmallIntegerField(default=31)

    # Conditional flags for task generation
    is_form_13f_applicable = models.BooleanField(default=False)
    is_form_crs_applicable = models.BooleanField(default=True)
    is_privacy_notice_annual_required = models.BooleanField(default=False)
    is_form_pf_applicable = models.BooleanField(default=False)
    has_material_brochure_changes = models.BooleanField(default=False)
    require_evidence_for_completion = models.BooleanField(default=False)

    # IARD renewal
    iard_renewal_window_start = models.DateField(null=True, blank=True)
    iard_renewal_window_end = models.DateField(null=True, blank=True)

    # Evidence settings
    upload_max_mb = models.PositiveIntegerField(default=25)

    # Monthly close
    monthly_close_due_day = models.PositiveSmallIntegerField(default=10)

    class Meta:
        verbose_name_plural = 'Compliance settings'

    def __str__(self):
        return f"Compliance Settings ({self.organization})"


class ComplianceTaskTemplate(SoftDeleteModel, OrganizationMixin):
    """Blueprint for recurring compliance tasks."""

    class Frequency(models.TextChoices):
        ONE_TIME = 'ONE_TIME', 'One Time'
        MONTHLY = 'MONTHLY', 'Monthly'
        QUARTERLY = 'QUARTERLY', 'Quarterly'
        ANNUAL = 'ANNUAL', 'Annual'

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, default='')
    frequency = models.CharField(max_length=20, choices=Frequency.choices)
    default_due_day = models.PositiveSmallIntegerField(null=True, blank=True)
    default_due_month = models.PositiveSmallIntegerField(null=True, blank=True)
    quarter = models.PositiveSmallIntegerField(null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True, default='')
    conditional_flag = models.CharField(max_length=100, blank=True, default='')
    owner_role = models.CharField(max_length=100, blank=True, default='')
    suggested_evidence = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['default_due_month', 'default_due_day', 'title']

    def __str__(self):
        return self.title


class ComplianceTask(SoftDeleteModel, OrganizationMixin):
    """Individual compliance task instance generated from a template."""

    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not Started'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        DEFERRED = 'DEFERRED', 'Deferred'
        NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'

    template = models.ForeignKey(
        ComplianceTaskTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instances'
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, default='')
    year = models.PositiveIntegerField(db_index=True)
    month = models.PositiveSmallIntegerField(db_index=True)
    due_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
        db_index=True
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_compliance_tasks'
    )
    notes = models.TextField(blank=True, default='')
    tags = models.CharField(max_length=500, blank=True, default='')
    conditional_flag = models.CharField(max_length=100, blank=True, default='')
    is_conditional = models.BooleanField(default=False)

    class Meta:
        ordering = ['due_date', 'title']

    def __str__(self):
        return f"{self.title} ({self.due_date})"

    @property
    def is_overdue(self):
        if self.status in (self.Status.COMPLETED, self.Status.NOT_APPLICABLE):
            return False
        return self.due_date < timezone.now().date()

    def mark_complete(self, user):
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.completed_by = user
        self.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])

    def mark_incomplete(self):
        self.status = self.Status.NOT_STARTED
        self.completed_at = None
        self.completed_by = None
        self.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])


class ComplianceEvidence(TimeStampedModel, OrganizationMixin):
    """Evidence/supporting document attached to a compliance task."""

    task = models.ForeignKey(
        ComplianceTask,
        on_delete=models.CASCADE,
        related_name='evidence_items'
    )
    file = models.FileField(upload_to='compliance/evidence/%Y/%m/', blank=True)
    original_filename = models.CharField(max_length=500, blank=True, default='')
    mime_type = models.CharField(max_length=255, blank=True, default='')
    size_bytes = models.PositiveBigIntegerField(default=0)
    external_link = models.URLField(max_length=2000, blank=True, default='')
    description = models.TextField(blank=True, default='')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_compliance_evidence'
    )

    class Meta:
        verbose_name_plural = 'Compliance evidence'
        ordering = ['-created_at']

    def __str__(self):
        return self.original_filename or self.external_link or f"Evidence #{self.pk}"


class ComplianceAuditLog(models.Model):
    """Immutable audit trail for compliance task changes."""

    class ActionType(models.TextChoices):
        STATUS_CHANGE = 'STATUS_CHANGE', 'Status Change'
        NOTE_EDIT = 'NOTE_EDIT', 'Note Edit'
        EVIDENCE_ADD = 'EVIDENCE_ADD', 'Evidence Added'
        EVIDENCE_REMOVE = 'EVIDENCE_REMOVE', 'Evidence Removed'
        TASK_EDIT = 'TASK_EDIT', 'Task Edit'
        TASK_CREATED = 'TASK_CREATED', 'Task Created'
        TEMPLATE_TOGGLE = 'TEMPLATE_TOGGLE', 'Template Toggle'

    task = models.ForeignKey(
        ComplianceTask,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='compliance_audit_logs'
    )
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='compliance_audit_actions'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action_type} on {self.task} at {self.created_at}"


class ComplianceDocument(SoftDeleteModel, OrganizationMixin):
    """General compliance document repository."""

    name = models.CharField(max_length=500)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=200, blank=True, default='')
    file = models.FileField(upload_to='compliance/documents/%Y/%m/')
    original_filename = models.CharField(max_length=500, blank=True, default='')
    file_type = models.CharField(max_length=100, blank=True, default='')
    file_size = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class SECNewsItem(models.Model):
    """SEC regulatory news feed items."""

    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='sec_news_items'
    )
    guid = models.CharField(max_length=500, db_index=True)
    title = models.CharField(max_length=1000)
    link = models.URLField(max_length=2000)
    description = models.TextField(blank=True, default='')
    published_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=200)
    is_read = models.BooleanField(default=False)
    is_relevant = models.BooleanField(default=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-published_at']
        unique_together = ['organization', 'guid']

    def __str__(self):
        return self.title
