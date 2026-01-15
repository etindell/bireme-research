from django.contrib import admin, messages

from apps.companies.models import Company

from .models import CompanyNews, BlacklistedDomain
from .services import fetch_and_store_news


def clear_all_news(modeladmin, request, queryset):
    """Delete ALL news items (ignores selection)."""
    count = CompanyNews.objects.count()
    CompanyNews.objects.all().delete()
    messages.success(request, f"Deleted {count} news items.")
clear_all_news.short_description = "🗑️ Clear ALL news (ignores selection)"


def fetch_fresh_news(modeladmin, request, queryset):
    """Fetch fresh news for all Long Book + Short Book companies."""
    companies = Company.objects.filter(
        is_deleted=False,
        status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK]
    )
    total = 0
    for company in companies:
        try:
            count = fetch_and_store_news(company)
            total += count
        except Exception as e:
            messages.warning(request, f"Error fetching {company.name}: {e}")
    messages.success(request, f"Fetched {total} new items for {companies.count()} companies.")
fetch_fresh_news.short_description = "🔄 Fetch fresh news for all portfolio companies"


@admin.register(CompanyNews)
class CompanyNewsAdmin(admin.ModelAdmin):
    list_display = ['headline', 'company', 'importance', 'event_type', 'published_at', 'is_read']
    list_filter = ['importance', 'source_type', 'event_type', 'is_read', 'organization']
    search_fields = ['headline', 'summary', 'company__name']
    readonly_fields = ['url_hash', 'fetched_at']
    date_hierarchy = 'published_at'
    ordering = ['-published_at']
    actions = [clear_all_news, fetch_fresh_news]


@admin.register(BlacklistedDomain)
class BlacklistedDomainAdmin(admin.ModelAdmin):
    list_display = ['domain', 'organization', 'created_at']
    list_filter = ['organization']
    search_fields = ['domain']
    ordering = ['domain']
