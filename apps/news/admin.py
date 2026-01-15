from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from apps.companies.models import Company

from .models import CompanyNews, BlacklistedDomain
from .services import fetch_and_store_news


@admin.register(CompanyNews)
class CompanyNewsAdmin(admin.ModelAdmin):
    list_display = ['headline', 'company', 'importance', 'event_type', 'published_at', 'is_read']
    list_filter = ['importance', 'source_type', 'event_type', 'is_read', 'organization']
    search_fields = ['headline', 'summary', 'company__name']
    readonly_fields = ['url_hash', 'fetched_at']
    date_hierarchy = 'published_at'
    ordering = ['-published_at']
    change_list_template = 'admin/news/companynews/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('fetch-news/', self.admin_site.admin_view(self.fetch_news_view), name='news_fetch'),
        ]
        return custom_urls + urls

    def fetch_news_view(self, request):
        """Custom view to fetch news - works even when list is empty."""
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
        return HttpResponseRedirect(reverse('admin:news_companynews_changelist'))


@admin.register(BlacklistedDomain)
class BlacklistedDomainAdmin(admin.ModelAdmin):
    list_display = ['domain', 'organization', 'created_at']
    list_filter = ['organization']
    search_fields = ['domain']
    ordering = ['domain']
