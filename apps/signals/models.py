"""
Signal tracking models for alternative-data research signals.
"""
from django.db import models
from django.conf import settings
from django.urls import reverse

from core.models import TimeStampedModel
from core.mixins import OrganizationMixin


class SignalSourceConfig(TimeStampedModel, OrganizationMixin):
    """
    Per-company signal source configuration.
    Each config ties one signal source to one company within an organization.
    """
    class Source(models.TextChoices):
        CYBOZU_CT_SUBDOMAINS = 'cybozu_ct_subdomains', 'Cybozu CT Subdomains'

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='signal_configs'
    )
    source = models.CharField(
        max_length=50,
        choices=Source.choices,
    )
    name = models.CharField(
        max_length=255,
        help_text='Display name for this signal config'
    )
    is_enabled = models.BooleanField(default=True)
    settings_json = models.JSONField(
        default=dict,
        blank=True,
        help_text='Source-specific settings'
    )
    ignore_keywords = models.JSONField(
        default=list,
        blank=True,
        help_text='Keywords to flag subdomains as non-candidate (e.g. test, staging)'
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'signal_source_configs'
        unique_together = ['organization', 'company', 'source']
        ordering = ['company__name', 'source']

    def __str__(self):
        return f'{self.company.name} - {self.get_source_display()}'

    def get_absolute_url(self):
        return reverse('signals:company_detail', kwargs={'company_slug': self.company.slug})

    @classmethod
    def get_cybozu_defaults(cls):
        """Return default settings and ignore_keywords for cybozu_ct_subdomains."""
        return {
            'settings_json': {
                'base_domains': ['cybozu.com', 'cybozu.cn', 'kintone.com'],
                'candidate_depth': 1,
                'verify_dns': False,
            },
            'ignore_keywords': [
                'test', 'staging', 'stage', 'dev', 'demo',
                'sandbox', 'qa', 'uat', 'internal', 'preview',
            ],
        }


class SignalSyncRun(models.Model):
    """
    Operational log of each sync execution.
    """
    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    config = models.ForeignKey(
        SignalSourceConfig,
        on_delete=models.CASCADE,
        related_name='sync_runs'
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    raw_items_seen = models.IntegerField(default=0)
    unique_domains_parsed = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    excluded_count = models.IntegerField(default=0)
    error_text = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'signal_sync_runs'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.config} sync @ {self.started_at:%Y-%m-%d %H:%M}'


class CertificateSubdomainObservation(models.Model):
    """
    One normalized observed subdomain candidate from certificate transparency logs.

    This is a proxy signal for customer acquisition activity, NOT a literal
    customer count. Each observation represents a subdomain seen in CT logs.
    """
    config = models.ForeignKey(
        SignalSourceConfig,
        on_delete=models.CASCADE,
        related_name='observations'
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        related_name='ct_observations',
        help_text='Denormalized FK for easier querying'
    )
    base_domain = models.CharField(max_length=255)
    fqdn = models.CharField(max_length=512)
    tenant_label = models.CharField(
        max_length=255,
        blank=True,
        help_text='e.g. "clientname" from clientname.kintone.com'
    )
    label_depth = models.PositiveSmallIntegerField(
        help_text='Number of labels before the base domain'
    )
    tenant_candidate = models.BooleanField(
        default=False,
        help_text='True if depth==1 and label is not in ignore list'
    )
    is_excluded = models.BooleanField(default=False)
    exclude_reason = models.CharField(max_length=255, blank=True)

    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    last_cert_logged_at = models.DateTimeField(null=True, blank=True)
    cert_not_before = models.DateTimeField(null=True, blank=True)
    cert_not_after = models.DateTimeField(null=True, blank=True)
    issuer_name = models.CharField(max_length=512, blank=True)
    observation_count = models.IntegerField(default=1)
    source_url = models.URLField(max_length=1024, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'certificate_subdomain_observations'
        unique_together = ['config', 'fqdn']
        indexes = [
            models.Index(fields=['company']),
            models.Index(fields=['base_domain']),
            models.Index(fields=['tenant_candidate']),
            models.Index(fields=['first_seen_at']),
            models.Index(fields=['last_seen_at']),
        ]

    def __str__(self):
        return self.fqdn
