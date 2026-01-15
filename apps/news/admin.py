from django.contrib import admin

from .models import CompanyNews


@admin.register(CompanyNews)
class CompanyNewsAdmin(admin.ModelAdmin):
    list_display = ['headline', 'company', 'importance', 'event_type', 'published_at', 'is_read']
    list_filter = ['importance', 'source_type', 'event_type', 'is_read', 'organization']
    search_fields = ['headline', 'summary', 'company__name']
    readonly_fields = ['url_hash', 'fetched_at']
    date_hierarchy = 'published_at'
    ordering = ['-published_at']
