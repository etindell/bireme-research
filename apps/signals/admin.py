from django.contrib import admin

from apps.signals.models import (
    CertificateSubdomainObservation,
    SignalSourceConfig,
    SignalSyncRun,
)


@admin.register(SignalSourceConfig)
class SignalSourceConfigAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'organization', 'company', 'source',
        'is_enabled', 'last_synced_at', 'created_at',
    ]
    list_filter = ['source', 'is_enabled', 'organization']
    search_fields = ['name', 'company__name']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'updated_by']
    raw_id_fields = ['company']

    fieldsets = (
        (None, {
            'fields': ('organization', 'company', 'source', 'name', 'is_enabled'),
        }),
        ('Configuration', {
            'fields': ('settings_json', 'ignore_keywords'),
        }),
        ('Sync', {
            'fields': ('last_synced_at',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',),
        }),
    )


@admin.register(SignalSyncRun)
class SignalSyncRunAdmin(admin.ModelAdmin):
    list_display = [
        'config', 'started_at', 'finished_at', 'status',
        'raw_items_seen', 'unique_domains_parsed',
        'created_count', 'updated_count', 'excluded_count',
    ]
    list_filter = ['status', 'config__source']
    readonly_fields = [
        'config', 'started_at', 'finished_at', 'status',
        'raw_items_seen', 'unique_domains_parsed',
        'created_count', 'updated_count', 'excluded_count',
        'error_text', 'metadata_json',
    ]


@admin.register(CertificateSubdomainObservation)
class CertificateSubdomainObservationAdmin(admin.ModelAdmin):
    list_display = [
        'fqdn', 'company', 'base_domain', 'tenant_label',
        'label_depth', 'tenant_candidate', 'is_excluded',
        'first_seen_at', 'last_seen_at', 'observation_count',
    ]
    list_filter = [
        'tenant_candidate', 'is_excluded', 'base_domain',
        'config__organization',
    ]
    search_fields = ['fqdn', 'tenant_label']
    readonly_fields = [
        'config', 'company', 'base_domain', 'fqdn',
        'first_seen_at', 'last_seen_at', 'observation_count',
        'raw_payload',
    ]
    raw_id_fields = ['config', 'company']
