"""
Views for Company management.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View

from django.shortcuts import redirect
from django.urls import reverse

from core.mixins import OrganizationViewMixin
from .models import Company, CompanyValuation
from .forms import CompanyForm, CompanyTickerFormSet, CompanyStatusForm, CompanyValuationForm
from .services import fetch_stock_price, update_valuation_prices


class CompanyListView(OrganizationViewMixin, ListView):
    """List all companies with filtering."""
    model = Company
    template_name = 'companies/company_list.html'
    context_object_name = 'companies'
    paginate_by = 25

    def get_queryset(self):
        from datetime import timedelta
        from django.utils import timezone

        status = self.request.GET.get('status')

        # When viewing "All Statuses", include recently deleted companies
        if not status:
            two_weeks_ago = timezone.now() - timedelta(weeks=2)
            qs = Company.all_objects.filter(
                organization=self.request.organization
            ).filter(
                # Not deleted OR deleted within 2 weeks
                models.Q(is_deleted=False) |
                models.Q(is_deleted=True, deleted_at__gte=two_weeks_ago)
            ).prefetch_related('tickers')
        else:
            # Status-filtered views exclude deleted companies
            qs = super().get_queryset().prefetch_related('tickers')
            qs = qs.filter(status=status)

        # Filter by sector
        sector = self.request.GET.get('sector')
        if sector:
            qs = qs.filter(sector=sector)

        # Search
        q = self.request.GET.get('q')
        if q:
            from django.contrib.postgres.search import SearchQuery
            qs = qs.filter(search_vector=SearchQuery(q, search_type='websearch'))

        # Ordering
        order = self.request.GET.get('order', 'name')
        if order == '-updated_at':
            qs = qs.order_by('-updated_at')
        else:
            qs = qs.order_by('name')

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = Company.Status.choices
        context['sectors'] = Company.Sector.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['current_sector'] = self.request.GET.get('sector', '')
        context['current_order'] = self.request.GET.get('order', 'name')
        context['search_query'] = self.request.GET.get('q', '')

        # For watchlist view, separate triggered alerts
        current_status = self.request.GET.get('status')
        if current_status == 'watchlist':
            context['is_watchlist_view'] = True
            # Get companies below alert price (triggered alerts)
            all_watchlist = Company.objects.filter(
                organization=self.request.organization,
                status=Company.Status.WATCHLIST,
                is_deleted=False,
                alert_price__isnull=False,
                current_price__isnull=False
            ).prefetch_related('tickers')

            context['triggered_alerts'] = [
                c for c in all_watchlist if c.is_alert_triggered
            ]

        # For portfolio and on_deck views, show expanded data
        if current_status in ['portfolio', 'on_deck']:
            context['is_expanded_view'] = True

        return context

    def get_template_names(self):
        if self.request.htmx:
            return ['companies/partials/company_list_content.html']
        return [self.template_name]


class CompanyDetailView(OrganizationViewMixin, DetailView):
    """Company detail page with notes."""
    model = Company
    template_name = 'companies/company_detail.html'
    context_object_name = 'company'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('tickers')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get notes for this company (primary + mentioned)
        from apps.notes.models import Note
        from django.db.models.functions import Coalesce

        context['notes'] = Note.objects.filter(
            organization=self.request.organization,
            is_deleted=False
        ).filter(
            models.Q(company=self.object) |
            models.Q(referenced_companies=self.object)
        ).select_related(
            'note_type', 'created_by', 'company'
        ).annotate(
            effective_date=Coalesce('written_at', 'created_at')
        ).order_by('-effective_date').distinct()[:50]

        context['statuses'] = Company.Status.choices
        return context


class CompanyCreateView(OrganizationViewMixin, CreateView):
    """Create a new company."""
    model = Company
    form_class = CompanyForm
    template_name = 'companies/company_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['ticker_formset'] = CompanyTickerFormSet(self.request.POST)
        else:
            context['ticker_formset'] = CompanyTickerFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ticker_formset = context['ticker_formset']

        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user

        if ticker_formset.is_valid():
            response = super().form_valid(form)
            ticker_formset.instance = self.object
            ticker_formset.save()
            messages.success(self.request, f'Company "{self.object.name}" created.')
            return response
        else:
            return self.form_invalid(form)


class CompanyUpdateView(OrganizationViewMixin, UpdateView):
    """Update a company."""
    model = Company
    form_class = CompanyForm
    template_name = 'companies/company_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['ticker_formset'] = CompanyTickerFormSet(self.request.POST, instance=self.object)
        else:
            context['ticker_formset'] = CompanyTickerFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ticker_formset = context['ticker_formset']

        form.instance.updated_by = self.request.user

        if ticker_formset.is_valid():
            response = super().form_valid(form)
            ticker_formset.save()
            messages.success(self.request, 'Company updated.')
            return response
        else:
            return self.form_invalid(form)


class CompanyDeleteView(OrganizationViewMixin, DeleteView):
    """Soft delete a company."""
    model = Company
    success_url = reverse_lazy('companies:list')

    def form_valid(self, form):
        self.object.delete(user=self.request.user)
        messages.success(self.request, f'Company "{self.object.name}" deleted.')
        return HttpResponse(status=204, headers={'HX-Redirect': self.success_url})


class CompanyStatusUpdateView(OrganizationViewMixin, View):
    """HTMX view to update company status."""

    def post(self, request, slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug
        )
        form = CompanyStatusForm(request.POST, instance=company)

        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()

            # Return updated status badge
            html = render_to_string(
                'companies/partials/status_badge.html',
                {'status': company.status, 'company': company},
                request=request
            )
            return HttpResponse(html)

        return HttpResponse(status=400)


# Import models for Q lookup
from django.db import models


class IRRLeaderboardView(OrganizationViewMixin, ListView):
    """IRR Leaderboard - companies ranked by IRR."""
    model = Company
    template_name = 'companies/irr_leaderboard.html'
    context_object_name = 'companies'

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related(
            'tickers', 'valuations'
        ).filter(
            valuations__is_active=True,
            valuations__is_deleted=False,
            valuations__calculated_irr__isnull=False
        ).order_by('-valuations__calculated_irr')

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        # Filter by sector
        sector = self.request.GET.get('sector')
        if sector:
            qs = qs.filter(sector=sector)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = Company.Status.choices
        context['sectors'] = Company.Sector.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['current_sector'] = self.request.GET.get('sector', '')
        return context

    def get_template_names(self):
        if self.request.htmx:
            return ['companies/partials/irr_leaderboard_items.html']
        return [self.template_name]


class CompanyValuationCreateView(OrganizationViewMixin, CreateView):
    """Create valuation for a company."""
    model = CompanyValuation
    form_class = CompanyValuationForm
    template_name = 'companies/valuation_form.html'

    def get_company(self):
        return get_object_or_404(
            Company.objects.filter(organization=self.request.organization),
            slug=self.kwargs['slug']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = self.get_company()
        return context

    def form_valid(self, form):
        company = self.get_company()
        form.instance.company = company
        form.instance.created_by = self.request.user

        # Try to fetch current price if ticker exists
        ticker = company.get_primary_ticker()
        if ticker and not form.instance.current_price:
            price_data = fetch_stock_price(ticker.symbol)
            if price_data:
                form.instance.current_price = price_data['price']
                form.instance.price_last_updated = price_data['timestamp']

        response = super().form_valid(form)
        messages.success(self.request, 'Valuation created.')
        return response

    def get_success_url(self):
        return reverse('companies:detail', kwargs={'slug': self.kwargs['slug']})


class CompanyValuationUpdateView(OrganizationViewMixin, UpdateView):
    """Update valuation."""
    model = CompanyValuation
    form_class = CompanyValuationForm
    template_name = 'companies/valuation_form.html'

    def get_queryset(self):
        return CompanyValuation.objects.filter(
            company__organization=self.request.organization,
            is_deleted=False
        ).prefetch_related('history')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = self.object.company
        context['valuation_history'] = self.object.history.all()[:20]
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        # Save with history tracking
        valuation = form.save(commit=False)
        valuation.save(history_user=self.request.user)
        messages.success(self.request, 'Valuation updated.')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('companies:detail', kwargs={'slug': self.object.company.slug})


class RefreshStockPriceView(OrganizationViewMixin, View):
    """HTMX view to refresh stock price for a valuation."""

    def post(self, request, pk):
        valuation = get_object_or_404(
            CompanyValuation.objects.filter(
                company__organization=request.organization
            ),
            pk=pk
        )

        ticker = valuation.company.get_primary_ticker()
        if not ticker:
            return HttpResponse(
                '<span class="text-red-600">No ticker found</span>',
                status=200
            )

        price_data = fetch_stock_price(ticker.symbol)
        if price_data:
            valuation.current_price = price_data['price']
            valuation.price_last_updated = price_data['timestamp']
            valuation.save()  # This will recalculate IRR

            html = render_to_string(
                'companies/partials/price_display.html',
                {'valuation': valuation},
                request=request
            )
            return HttpResponse(html)

        return HttpResponse(
            '<span class="text-red-600">Failed to fetch price</span>',
            status=200
        )


class RefreshAllPricesView(OrganizationViewMixin, View):
    """Refresh all stock prices for organization."""

    def post(self, request):
        count = update_valuation_prices(organization=request.organization)
        messages.success(request, f'Updated prices for {count} companies.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('companies:irr_leaderboard')


class RefreshWatchlistPricesView(OrganizationViewMixin, View):
    """Refresh all stock prices for watchlist companies."""

    def post(self, request):
        from django.utils import timezone

        watchlist_companies = Company.objects.filter(
            organization=request.organization,
            status=Company.Status.WATCHLIST,
            is_deleted=False
        ).prefetch_related('tickers')

        count = 0
        for company in watchlist_companies:
            ticker = company.get_primary_ticker()
            if ticker:
                price_data = fetch_stock_price(ticker.symbol)
                if price_data:
                    company.current_price = price_data['price']
                    company.ev_ebitda = price_data.get('ev_ebitda')
                    company.market_cap = price_data.get('market_cap')
                    if price_data.get('business_summary') and not company.business_summary:
                        company.business_summary = price_data['business_summary']
                    company.price_last_updated = timezone.now()
                    company.save(update_fields=[
                        'current_price', 'ev_ebitda', 'market_cap',
                        'business_summary', 'price_last_updated'
                    ])
                    count += 1

        messages.success(request, f'Updated prices for {count} watchlist companies.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('companies:list')


class RefreshCompanyPricesView(OrganizationViewMixin, View):
    """Refresh stock prices for Portfolio and On Deck companies."""

    def post(self, request):
        from django.utils import timezone

        status_filter = request.GET.get('status', '')

        # Filter by status if provided, otherwise refresh Portfolio and On Deck
        if status_filter:
            companies = Company.objects.filter(
                organization=request.organization,
                status=status_filter,
                is_deleted=False
            ).prefetch_related('tickers')
        else:
            companies = Company.objects.filter(
                organization=request.organization,
                status__in=[Company.Status.PORTFOLIO, Company.Status.ON_DECK],
                is_deleted=False
            ).prefetch_related('tickers')

        count = 0
        for company in companies:
            ticker = company.get_primary_ticker()
            if ticker:
                price_data = fetch_stock_price(ticker.symbol)
                if price_data:
                    company.current_price = price_data['price']
                    company.ev_ebitda = price_data.get('ev_ebitda')
                    company.market_cap = price_data.get('market_cap')
                    if price_data.get('business_summary') and not company.business_summary:
                        company.business_summary = price_data['business_summary']
                    company.price_last_updated = timezone.now()
                    company.save(update_fields=[
                        'current_price', 'ev_ebitda', 'market_cap',
                        'business_summary', 'price_last_updated'
                    ])
                    count += 1

        messages.success(request, f'Updated data for {count} companies.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('companies:list')


class UpgradeToOnDeckView(OrganizationViewMixin, View):
    """Upgrade a company from Watchlist to On Deck."""

    def post(self, request, slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug
        )

        company.status = Company.Status.ON_DECK
        company.updated_by = request.user
        company.save(update_fields=['status', 'updated_by', 'updated_at'])

        messages.success(request, f'{company.name} moved to On Deck.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('companies:detail', slug=slug)
