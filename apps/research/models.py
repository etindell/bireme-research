"""
Models for deep research automation.

ResearchProfile: Per-company metadata used to generate research prompts
    (IR URL, executive names, search terms).
ResearchJob: History of research runs for audit/reuse.
"""
from django.db import models
from django.conf import settings

from core.models import TimeStampedModel, SoftDeleteModel
from core.mixins import OrganizationMixin


class ResearchProfile(TimeStampedModel):
    """
    Per-company research metadata. Stores the IR URL, executive names,
    and custom search terms that get injected into the Claude Code prompt.

    Auto-created the first time the Deep Research button is clicked;
    fields can be edited in the modal before generating the prompt.
    """
    company = models.OneToOneField(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='research_profile',
    )

    # Investor relations
    ir_url = models.URLField(
        blank=True,
        help_text='Investor Relations page URL (auto-detected or manual)',
    )

    # Key people to search for
    ceo_name = models.CharField(max_length=255, blank=True)
    cfo_name = models.CharField(max_length=255, blank=True)
    other_executives = models.TextField(
        blank=True,
        help_text='Other executives to search for, one per line',
    )

    # Custom search terms (in addition to company name + ticker)
    extra_search_terms = models.TextField(
        blank=True,
        help_text='Additional search terms for YouTube/podcast, one per line',
    )

    # Exclusions
    exclude_domains = models.TextField(
        blank=True,
        help_text='Domains to skip when scraping, one per line',
    )

    class Meta:
        db_table = 'research_profiles'

    def __str__(self):
        return f'Research profile: {self.company.name}'

    def get_executive_names(self):
        """Return list of all executive names."""
        names = []
        if self.ceo_name:
            names.append(self.ceo_name)
        if self.cfo_name:
            names.append(self.cfo_name)
        if self.other_executives:
            names.extend(
                n.strip() for n in self.other_executives.strip().split('\n') if n.strip()
            )
        return names

    def get_extra_search_terms(self):
        """Return list of extra search terms."""
        if not self.extra_search_terms:
            return []
        return [t.strip() for t in self.extra_search_terms.strip().split('\n') if t.strip()]


class ResearchJob(SoftDeleteModel, OrganizationMixin):
    """
    Record of a research prompt that was generated (and optionally executed).

    Tracks what was generated so you can re-run or reference past research.
    """
    class Status(models.TextChoices):
        GENERATED = 'generated', 'Prompt Generated'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='research_jobs',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.GENERATED,
    )

    # The generated prompt (stored for reference)
    prompt_text = models.TextField(
        help_text='The Claude Code prompt that was generated',
    )

    # What configuration was used
    config_snapshot = models.JSONField(
        default=dict,
        help_text='Snapshot of ResearchProfile fields at generation time',
    )

    # Results (filled in manually after Claude Code run)
    notebook_url = models.URLField(blank=True, help_text='NotebookLM or Drive folder URL')
    files_found = models.PositiveIntegerField(default=0, help_text='Number of documents found')
    videos_found = models.PositiveIntegerField(default=0, help_text='Number of videos found')
    notes_text = models.TextField(blank=True, help_text='Freeform notes about the run')

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'research_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.company.name} research ({self.created_at:%Y-%m-%d})'
