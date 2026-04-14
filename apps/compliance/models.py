import uuid

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
    survey_template = models.ForeignKey(
        'SurveyTemplate', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='task_templates',
    )

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
    migrated_to_survey = models.ForeignKey(
        'SurveyAssignment', on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='migrated_from_tasks'
    )
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
    text_content = models.TextField(blank=True, default='')
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


# ============ Compliance Survey System ============

class SurveyTemplate(TimeStampedModel, OrganizationMixin):
    """Blueprint for a compliance survey or certification."""

    class Cadence(models.TextChoices):
        ONE_TIME = 'ONE_TIME', 'One Time'
        QUARTERLY = 'QUARTERLY', 'Quarterly'
        ANNUAL = 'ANNUAL', 'Annual'
        EVENT_DRIVEN = 'EVENT_DRIVEN', 'Event Driven'

    class AudienceType(models.TextChoices):
        ALL_SUPERVISED = 'ALL_SUPERVISED', 'All Supervised Persons'
        ACCESS_PERSONS = 'ACCESS_PERSONS', 'Access Persons'
        COVERED_ASSOCIATES = 'COVERED_ASSOCIATES', 'CoverED Associates'
        CCO_ONLY = 'CCO_ONLY', 'CCO Only'
        SELECTED_USERS = 'SELECTED_USERS', 'Selected Users'

    slug = models.SlugField(max_length=100)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    cadence = models.CharField(max_length=20, choices=Cadence.choices, default=Cadence.ANNUAL)
    audience_type = models.CharField(max_length=30, choices=AudienceType.choices, default=AudienceType.ALL_SUPERVISED)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['organization', 'slug']
        ordering = ['name']

    def __str__(self):
        return self.name


class SurveyVersion(TimeStampedModel, OrganizationMixin):
    """A specific version of a survey template. Immutable once published."""

    template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=False)
    effective_date = models.DateField(default=timezone.now)
    archived_date = models.DateField(null=True, blank=True)
    instructions = models.TextField(blank=True, default='')
    attestation_text = models.TextField(
        help_text="Final legal attestation language the user must agree to.",
        default="I hereby certify that the information provided is true and correct to the best of my knowledge."
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ['template', 'version_number']

    def __str__(self):
        return f"{self.template.name} (v{self.version_number})"


class SurveyQuestion(models.Model):
    """An individual question within a survey version."""

    class FieldType(models.TextChoices):
        YES_NO = 'YES_NO', 'Yes/No'
        TEXT = 'TEXT', 'Short Text'
        LONG_TEXT = 'LONG_TEXT', 'Long Text'
        DATE = 'DATE', 'Date'
        DECIMAL = 'DECIMAL', 'Decimal'
        FILE = 'FILE', 'File Upload'
        SINGLE_SELECT = 'SINGLE_SELECT', 'Single Select'
        MULTI_SELECT = 'MULTI_SELECT', 'Multi Select'
        ACCOUNT_TABLE = 'ACCOUNT_TABLE', 'Account Table'
        TRANSACTION_TABLE = 'TRANSACTION_TABLE', 'Transaction Table'

    version = models.ForeignKey(SurveyVersion, on_delete=models.CASCADE, related_name='questions')
    sort_order = models.PositiveIntegerField(default=0)
    question_key = models.SlugField(max_length=100, help_text="Used for data extraction/rules")
    prompt = models.TextField()
    help_text = models.TextField(blank=True, default='')
    field_type = models.CharField(max_length=30, choices=FieldType.choices, default=FieldType.YES_NO)
    is_required = models.BooleanField(default=True)
    
    # JSON Configs
    conditional_logic = models.JSONField(
        null=True, blank=True, help_text="Rules for when to show this question"
    )
    response_options = models.JSONField(
        null=True, blank=True, help_text="Options for select fields (list of strings or key/value pairs)"
    )
    exception_trigger_rules = models.JSONField(
        null=True, blank=True, help_text="Rules that trigger a SurveyException based on answer"
    )

    class Meta:
        ordering = ['sort_order']
        unique_together = ['version', 'question_key']

    def __str__(self):
        return f"{self.question_key}: {self.prompt[:50]}..."


class SurveyDistribution(TimeStampedModel, OrganizationMixin):
    """A batch send event that groups assignments and links to a ComplianceTask."""

    version = models.ForeignKey(SurveyVersion, on_delete=models.CASCADE, related_name='distributions')
    compliance_task = models.OneToOneField(
        'ComplianceTask', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='survey_distribution'
    )
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    email_sent = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Distribution of {self.version} on {self.sent_at}"


class SurveyAssignment(TimeStampedModel, OrganizationMixin):
    """An instance of a survey assigned to a specific user for a specific period."""

    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not Started'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        SUBMITTED = 'SUBMITTED', 'Submitted'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        OVERDUE = 'OVERDUE', 'Overdue'
        NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'

    version = models.ForeignKey(SurveyVersion, on_delete=models.PROTECT, related_name='assignments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='survey_assignments')
    distribution = models.ForeignKey(
        'SurveyDistribution', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assignments'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    due_date = models.DateField(db_index=True)
    
    # Period scoping
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    quarter = models.PositiveSmallIntegerField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED, db_index=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_surveys'
    )
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='', help_text="CCO notes when rejecting a submission")

    class Meta:
        ordering = ['due_date', 'user__email']
        # Prevent duplicate assignments for the same period/user/version
        unique_together = ['version', 'user', 'period_start', 'period_end', 'year', 'quarter']

    def __str__(self):
        return f"{self.user.email} - {self.version.template.name}"


class SurveyResponse(TimeStampedModel, OrganizationMixin):
    """Metadata for a submitted survey."""

    assignment = models.OneToOneField(SurveyAssignment, on_delete=models.CASCADE, related_name='response')
    attested_name = models.CharField(max_length=255, help_text="Digital signature")
    attested_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='', help_text="Internal notes or migration source info")
    certification_text_snapshot = models.TextField(help_text="Snapshot of legal text at time of signing")

    def __str__(self):
        return f"Response for {self.assignment}"


class SurveyAnswer(models.Model):
    """A specific answer to a question in a response."""

    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT)
    value_json = models.JSONField(null=True, blank=True)
    is_exception_flag = models.BooleanField(default=False)
    exception_summary = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ['response', 'question']

    def __str__(self):
        return f"Answer to {self.question.question_key} by {self.response.assignment.user}"


class SurveyEvidenceUpload(TimeStampedModel, OrganizationMixin):
    """File attached to a survey response or specific answer."""

    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='evidence_files')
    answer = models.ForeignKey(SurveyAnswer, on_delete=models.SET_NULL, null=True, blank=True, related_name='evidence_files')
    file = models.FileField(upload_to='compliance/survey_evidence/%Y/%m/')
    original_filename = models.CharField(max_length=500)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return self.original_filename


class SurveyException(TimeStampedModel, OrganizationMixin):
    """A compliance exception or escalation generated from a survey."""

    class Severity(models.TextChoices):
        INFO = 'INFO', 'Information'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'

    class Category(models.TextChoices):
        TRADE_ERROR = 'TRADE_ERROR', 'Trade Error'
        COMPLAINT = 'COMPLAINT', 'Client Complaint'
        CODE_VIOLATION = 'CODE_VIOLATION', 'Code of Ethics Violation'
        POLITICAL_CONTRIBUTION = 'POLITICAL_CONTRIBUTION', 'Political Contribution'
        OBA = 'OBA', 'Outside Business Activity'
        CYBERSECURITY = 'CYBERSECURITY', 'Cybersecurity Incident'
        OFF_CHANNEL_COMMS = 'OFF_CHANNEL_COMMS', 'Off-Channel Communications'
        PERSONAL_TRADE_ISSUE = 'PERSONAL_TRADE_ISSUE', 'Personal Trading Issue'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
        RESOLVED = 'RESOLVED', 'Resolved'
        DISMISSED = 'DISMISSED', 'Dismissed'

    assignment = models.ForeignKey(SurveyAssignment, on_delete=models.CASCADE, related_name='exceptions')
    response = models.ForeignKey(SurveyResponse, on_delete=models.SET_NULL, null=True, blank=True, related_name='exceptions')
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    summary = models.CharField(max_length=500)
    details = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_exceptions'
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-opened_at']

    def __str__(self):
        return f"{self.category} - {self.assignment.user.email}"


class EmployeeCertificationStatus(TimeStampedModel, OrganizationMixin):
    """Aggregated status of an employee's compliance certifications."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='compliance_status')
    is_access_person = models.BooleanField(default=False)
    is_covered_associate = models.BooleanField(default=False)
    last_annual_attestation_date = models.DateField(null=True, blank=True)
    last_quarterly_reporting_date = models.DateField(null=True, blank=True)
    outstanding_assignments_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Employee certification statuses'

    def __str__(self):
        return f"Status: {self.user.email}"
