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

        # Unread count
        context['unread_count'] = CompanyNews.objects.filter(
            organization=self.request.organization,
            is_read=False
        ).count()

        # Preference profile
        context['preference_profile'] = self.request.organization.get_news_preference_profile()

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


class SetNewsFeedbackView(OrganizationViewMixin, View):
    """Set thumbs-up/down feedback for a news item (HTMX)."""

    def post(self, request, pk):
        news = get_object_or_404(
            CompanyNews,
            pk=pk,
            organization=request.organization
        )
        value = request.POST.get('feedback')
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = None

        # Toggle: clicking the same feedback again clears it
        if news.feedback == value:
            news.feedback = None
        else:
            news.feedback = value
        news.save(update_fields=['feedback'])

        # Thumbs-down: remove the item from the list
        if news.feedback == CompanyNews.Feedback.THUMBS_DOWN:
            return HttpResponse('')

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


class ClearAllNewsView(OrganizationViewMixin, View):
    """Delete all news items for this organization."""

    def post(self, request):
        count, _ = CompanyNews.objects.filter(
            organization=request.organization
        ).delete()
        messages.success(request, f'Cleared {count} news items.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        from django.shortcuts import redirect
        return redirect('news:dashboard')


class FetchAllNewsView(OrganizationViewMixin, View):
    """Fetch fresh news for all portfolio companies (runs in background)."""

    def post(self, request):
        import threading
        from django.db import connection
        from .services import fetch_news_for_companies

        companies = list(
            Company.objects.filter(
                organization=request.organization,
                is_deleted=False,
                status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK]
            ).select_related('organization').prefetch_related('tickers')
        )

        if not companies:
            messages.info(request, 'No portfolio companies to fetch news for.')
        else:
            def _run():
                try:
                    fetch_news_for_companies(companies)
                finally:
                    connection.close()

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            messages.info(request, f'Fetching news for {len(companies)} companies in the background. Refresh in a minute to see results.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        from django.shortcuts import redirect
        return redirect('news:dashboard')
