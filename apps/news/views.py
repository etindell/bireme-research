"""
Views for the news feature.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView

from core.mixins import OrganizationViewMixin
from apps.companies.models import Company
from .models import CompanyNews, BlacklistedDomain


class NewsDashboardView(OrganizationViewMixin, ListView):
    """Aggregated news feed for all portfolio companies."""
    model = CompanyNews
    template_name = 'news/dashboard.html'
    context_object_name = 'news_items'
    paginate_by = 50

    def get_queryset(self):
        qs = CompanyNews.objects.filter(
            organization=self.request.organization
        ).select_related('company')

        # Filter by importance
        importance = self.request.GET.get('importance')
        if importance:
            qs = qs.filter(importance=importance)

        # Filter by company
        company_slug = self.request.GET.get('company')
        if company_slug:
            qs = qs.filter(company__slug=company_slug)

        # Filter by source type
        source_type = self.request.GET.get('source')
        if source_type:
            qs = qs.filter(source_type=source_type)

        # Filter by read status
        if self.request.GET.get('unread') == '1':
            qs = qs.filter(is_read=False)

        # Filter by starred
        if self.request.GET.get('starred') == '1':
            qs = qs.filter(is_starred=True)

        return qs.order_by('-published_at')

    def get_template_names(self):
        if self.request.htmx and not self.request.htmx.boosted:
            return ['news/partials/news_list.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get companies for filter dropdown
        context['companies'] = Company.objects.filter(
            organization=self.request.organization,
            status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK],
            is_deleted=False
        ).order_by('name')

        # Current filter values
        context['current_importance'] = self.request.GET.get('importance', '')
        context['current_company'] = self.request.GET.get('company', '')
        context['current_source'] = self.request.GET.get('source', '')
        context['show_unread'] = self.request.GET.get('unread') == '1'
        context['show_starred'] = self.request.GET.get('starred') == '1'

        # Unread count
        context['unread_count'] = CompanyNews.objects.filter(
            organization=self.request.organization,
            is_read=False
        ).count()

        return context


class CompanyNewsView(OrganizationViewMixin, ListView):
    """News section for a specific company (embedded in company detail)."""
    model = CompanyNews
    template_name = 'news/partials/company_news.html'
    context_object_name = 'news_items'

    def get_queryset(self):
        return CompanyNews.objects.filter(
            company__slug=self.kwargs['slug'],
            company__organization=self.request.organization
        ).order_by('-published_at')[:20]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = get_object_or_404(
            Company,
            slug=self.kwargs['slug'],
            organization=self.request.organization
        )
        return context


class ToggleNewsReadView(OrganizationViewMixin, View):
    """Toggle read status for a news item (HTMX)."""

    def post(self, request, pk):
        news = get_object_or_404(
            CompanyNews,
            pk=pk,
            organization=request.organization
        )
        news.is_read = not news.is_read
        news.save(update_fields=['is_read'])

        return render(
            request,
            'news/partials/news_item.html',
            {'item': news}
        )


class ToggleNewsStarredView(OrganizationViewMixin, View):
    """Toggle starred status for a news item (HTMX)."""

    def post(self, request, pk):
        news = get_object_or_404(
            CompanyNews,
            pk=pk,
            organization=request.organization
        )
        news.is_starred = not news.is_starred
        news.save(update_fields=['is_starred'])

        return render(
            request,
            'news/partials/news_item.html',
            {'item': news}
        )


class RefreshCompanyNewsView(OrganizationViewMixin, View):
    """Manually refresh news for a specific company (HTMX)."""

    def post(self, request, slug):
        from .services import fetch_and_store_news

        company = get_object_or_404(
            Company,
            slug=slug,
            organization=request.organization
        )

        try:
            count = fetch_and_store_news(company)
            if count > 0:
                messages.success(request, f'Found {count} new news items.')
            else:
                messages.info(request, 'No new news items found.')
        except Exception as e:
            messages.error(request, f'Failed to fetch news: {e}')

        # Return updated news list
        news_items = CompanyNews.objects.filter(
            company=company
        ).order_by('-published_at')[:20]

        return render(
            request,
            'news/partials/company_news.html',
            {'news_items': news_items, 'company': company}
        )


class MarkAllReadView(OrganizationViewMixin, View):
    """Mark all news items as read."""

    def post(self, request):
        CompanyNews.objects.filter(
            organization=request.organization,
            is_read=False
        ).update(is_read=True)

        messages.success(request, 'All news items marked as read.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return HttpResponse(status=204)


class BlacklistDomainView(OrganizationViewMixin, View):
    """Blacklist a domain from future news fetches."""

    def post(self, request, pk):
        news = get_object_or_404(
            CompanyNews,
            pk=pk,
            organization=request.organization
        )

        domain = news.source_domain
        if domain:
            BlacklistedDomain.objects.get_or_create(
                organization=request.organization,
                domain=domain
            )
            messages.success(request, f'"{domain}" will be excluded from future news fetches.')

        return render(
            request,
            'news/partials/news_item.html',
            {'item': news}
        )


class UnblacklistDomainView(OrganizationViewMixin, View):
    """Remove a domain from the blacklist."""

    def post(self, request, domain):
        BlacklistedDomain.objects.filter(
            organization=request.organization,
            domain=domain
        ).delete()

        messages.success(request, f'"{domain}" has been removed from the blacklist.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return HttpResponse(status=204)


class BlacklistManageView(OrganizationViewMixin, ListView):
    """Manage blacklisted domains."""
    model = BlacklistedDomain
    template_name = 'news/blacklist.html'
    context_object_name = 'domains'

    def get_queryset(self):
        return BlacklistedDomain.objects.filter(
            organization=self.request.organization
        ).order_by('domain')


class FetchAllNewsView(OrganizationViewMixin, View):
    """Fetch fresh news for all portfolio companies."""

    def post(self, request):
        from .services import fetch_news_for_companies

        companies = Company.objects.filter(
            organization=request.organization,
            is_deleted=False,
            status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK]
        )

        total, errors = fetch_news_for_companies(companies)

        if total > 0:
            messages.success(request, f'Fetched {total} news items for {companies.count()} companies.')
        else:
            messages.info(request, 'No new news items found.')

        for error in errors[:3]:  # Show max 3 errors
            messages.warning(request, error)

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        from django.shortcuts import redirect
        return redirect('news:dashboard')
