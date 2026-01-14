"""
Views for Company management.
"""
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View

from django.shortcuts import redirect, render
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
        from django.db.models import Exists, OuterRef
        from apps.notes.models import NoteCashFlow

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

        # Filter by direction (for On Deck view)
        direction = self.request.GET.get('direction')
        if direction:
            qs = qs.filter(direction=direction)

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

        # Annotate with has_irr to identify companies that need IRR input
        has_irr_subquery = NoteCashFlow.objects.filter(
            note__company=OuterRef('pk'),
            note__is_deleted=False
        )
        qs = qs.annotate(has_irr=Exists(has_irr_subquery))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = Company.Status.choices
        context['sectors'] = Company.Sector.choices
        context['directions'] = Company.Direction.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['current_sector'] = self.request.GET.get('sector', '')
        context['current_direction'] = self.request.GET.get('direction', '')
        context['current_order'] = self.request.GET.get('order', 'name')
        context['search_query'] = self.request.GET.get('q', '')

        # For watchlist view, separate triggered alerts by type
        current_status = self.request.GET.get('status')
        if current_status == 'watchlist':
            context['is_watchlist_view'] = True
            # Get all watchlist companies with prices
            all_watchlist = Company.objects.filter(
                organization=self.request.organization,
                status=Company.Status.WATCHLIST,
                is_deleted=False,
                current_price__isnull=False
            ).prefetch_related('tickers')

            # Separate low and high alerts
            context['triggered_low_alerts'] = [
                c for c in all_watchlist if c.is_low_alert_triggered
            ]
            context['triggered_high_alerts'] = [
                c for c in all_watchlist if c.is_high_alert_triggered
            ]
            # Combined for backward compatibility
            context['triggered_alerts'] = [
                c for c in all_watchlist if c.is_alert_triggered
            ]

        # For long_book, short_book and on_deck views, show expanded data
        if current_status in ['long_book', 'short_book', 'on_deck']:
            context['is_expanded_view'] = True

        return context

    def get_template_names(self):
        # Only return partial for targeted HTMX requests (like filter changes)
        # Boosted requests (sidebar link clicks) should get the full template
        if self.request.htmx and not self.request.htmx.boosted:
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

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()

        # Handle file upload - need to pass FILES to form
        if request.FILES.get('notes_file'):
            form = CompanyForm(request.POST, request.FILES)

        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        context = self.get_context_data()
        ticker_formset = context['ticker_formset']

        # Check if we have a notes file to import
        notes_file = self.request.FILES.get('notes_file')
        notes_data = []
        company_name_from_file = None

        if notes_file:
            content = notes_file.read().decode('utf-8')
            company_name_from_file, notes_data = self._parse_notes_file(content)

            # If company name field is empty, use name from file
            if not form.cleaned_data.get('name') and company_name_from_file:
                form.instance.name = company_name_from_file

        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user

        if ticker_formset.is_valid():
            response = super().form_valid(form)
            ticker_formset.instance = self.object
            ticker_formset.save()

            # Import notes if we have any
            if notes_data:
                from apps.notes.models import Note
                created_count = 0
                for note_data in notes_data:
                    title = note_data['title'][:500] if note_data['title'] else 'Imported note'
                    if len(title) > 100:
                        title = title[:97] + '...'

                    Note.objects.create(
                        organization=self.request.organization,
                        company=self.object,
                        title=title,
                        content=note_data['content'],
                        written_at=note_data['written_at'],
                        is_imported=True,
                        created_by=self.request.user,
                    )
                    created_count += 1

                messages.success(self.request, f'Company "{self.object.name}" created with {created_count} imported notes.')
            else:
                messages.success(self.request, f'Company "{self.object.name}" created.')

            return response
        else:
            return self.form_invalid(form)

    def _parse_notes_file(self, content):
        """
        Parse notes file for company creation.

        Supports two formats:

        Format 1 (plain text company name):
        Company Name
        - Date - Note title
          - Content (bold/underlined)

        Format 2 (bullet company name):
        - Company Name
          - Date - Note title
            - Content (bold/underlined)
        """
        import re
        from datetime import datetime
        from django.utils import timezone

        lines = content.split('\n')

        # Detect format: check if first non-empty line is a bullet
        is_bullet_format = False
        for line in lines:
            stripped = line.strip()
            if stripped:
                is_bullet_format = stripped.startswith('-')
                break

        def parse_date(date_str):
            date_str = date_str.replace('\ufeff', '').strip()
            formats = [
                "%a, %b %d, %Y", "%A, %b %d, %Y", "%a, %B %d, %Y",
                "%b %d, %Y", "%B %d, %Y", "%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return timezone.make_aware(datetime.combine(dt.date(), datetime.min.time()))
                except ValueError:
                    continue
            return None

        def extract_date_from_text(text):
            text = text.replace('\ufeff', '').strip()
            patterns = [
                (r'([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})', '%a, %b %d, %Y'),
                (r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', '%b %d, %Y'),
                (r'(\d{1,2}/\d{1,2}/\d{2,4})', None),
            ]
            for pattern, _ in patterns:
                match = re.search(pattern, text)
                if match:
                    date_str = match.group(1)
                    parsed_date = parse_date(date_str)
                    if parsed_date:
                        text_without_date = text[:match.start()] + text[match.end():]
                        text_without_date = re.sub(r'\s+', ' ', text_without_date).strip()
                        text_without_date = text_without_date.strip('-').strip()
                        return parsed_date, text_without_date
            return None, text

        def get_indent_level(line):
            stripped = line.lstrip()
            if not stripped.startswith('-'):
                return -1
            indent = len(line) - len(line.lstrip())
            if indent == 0:
                return 1
            elif indent <= 4:
                return 2
            else:
                return 3

        notes = []
        company_name = None
        current_note = None
        current_content_lines = []

        if is_bullet_format:
            # Format 2: - Company Name / - Note title / - Content
            for line in lines:
                stripped = line.strip()

                if not stripped:
                    if current_note and current_content_lines:
                        current_content_lines.append('')
                    continue

                if not stripped.startswith('-'):
                    if current_note:
                        current_content_lines.append(stripped)
                    continue

                level = get_indent_level(line)
                bullet_text = stripped[1:].strip()

                if level == 1:
                    # Company name
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)
                        current_note = None
                        current_content_lines = []
                    company_name = bullet_text

                elif level == 2:
                    # Note title with date
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)

                    parsed_date, title = extract_date_from_text(bullet_text)
                    current_note = {
                        'written_at': parsed_date,
                        'title': title if title else bullet_text,
                        'content': '',
                    }
                    current_content_lines = []

                elif level == 3 and current_note:
                    # Note content at section header level - bold/underline (unless #mythoughts)
                    if '#mythoughts' not in bullet_text.lower():
                        bullet_text = f"**__{bullet_text}__**"
                    current_content_lines.append(bullet_text)

                elif level > 3 and current_note:
                    # Deeper content - no formatting
                    current_content_lines.append(bullet_text)
        else:
            # Format 1: Company Name (plain text) / - Note title / - Content
            found_company = False
            for line in lines:
                stripped = line.strip()

                if not stripped:
                    if current_note and current_content_lines:
                        current_content_lines.append('')
                    continue

                # First non-empty, non-bullet line is company name
                if not found_company and not stripped.startswith('-'):
                    company_name = stripped
                    found_company = True
                    continue

                if not stripped.startswith('-'):
                    if current_note:
                        current_content_lines.append(stripped)
                    continue

                level = get_indent_level(line)
                bullet_text = stripped[1:].strip()

                if level == 1:
                    # Note title with date
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)

                    parsed_date, title = extract_date_from_text(bullet_text)
                    current_note = {
                        'written_at': parsed_date,
                        'title': title if title else bullet_text,
                        'content': '',
                    }
                    current_content_lines = []

                elif level == 2 and current_note:
                    # Note content at section header level - bold/underline (unless #mythoughts)
                    if '#mythoughts' not in bullet_text.lower():
                        bullet_text = f"**__{bullet_text}__**"
                    current_content_lines.append(bullet_text)

                elif level > 2 and current_note:
                    # Deeper content - no formatting
                    current_content_lines.append(bullet_text)

        # Save last note
        if current_note:
            current_note['content'] = '\n'.join(current_content_lines).strip()
            notes.append(current_note)

        # Fill in missing dates
        last_known_date = None
        for note in reversed(notes):
            if note['written_at']:
                last_known_date = note['written_at']
            elif last_known_date:
                note['written_at'] = last_known_date

        return company_name, notes


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

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete(user=request.user)
        messages.success(request, f'Company "{self.object.name}" deleted.')
        return HttpResponse(status=204, headers={'HX-Redirect': str(self.success_url)})


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
        # Only return partial for targeted HTMX requests (not boosted navigation)
        if self.request.htmx and not self.request.htmx.boosted:
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
                status__in=[Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK, Company.Status.ON_DECK],
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

        # Get direction from POST data or infer from alert type
        direction = request.POST.get('direction')
        if not direction:
            # Infer from which alert triggered
            if company.is_low_alert_triggered:
                direction = Company.Direction.LONG
            elif company.is_high_alert_triggered:
                direction = Company.Direction.SHORT
            else:
                direction = Company.Direction.LONG  # Default to long

        company.status = Company.Status.ON_DECK
        company.direction = direction
        company.updated_by = request.user
        company.save(update_fields=['status', 'direction', 'updated_by', 'updated_at'])

        direction_display = 'Long' if direction == Company.Direction.LONG else 'Short'
        messages.success(request, f'{company.name} moved to On Deck ({direction_display}).')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('companies:detail', slug=slug)


class GenerateSummaryView(OrganizationViewMixin, View):
    """Generate AI summary for a company's notes."""

    def post(self, request, slug):
        from apps.companies.services import generate_company_summary

        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug
        )

        focus_topic = request.POST.get('focus_topic', '').strip() or None
        summary = generate_company_summary(company, focus_topic=focus_topic)

        if summary:
            messages.success(request, 'Summary generated successfully.')
        else:
            messages.error(request, 'Failed to generate summary. Check that ANTHROPIC_API_KEY is set.')

        if request.htmx:
            # Return the updated summary partial
            return render(
                request,
                'companies/partials/summary_section.html',
                {'company': company}
            )
        return redirect('companies:detail', slug=slug)


class ForecastHistoryAPIView(OrganizationViewMixin, View):
    """API endpoint returning historical forecast data for charting."""

    def get(self, request, slug):
        from apps.notes.models import NoteCashFlow

        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug
        )

        # Get all NoteCashFlow records for this company's notes, ordered by date
        cash_flows = NoteCashFlow.objects.filter(
            note__company=company,
            note__is_deleted=False
        ).select_related('note').order_by('note__created_at')

        data = {
            'company': company.name,
            'profitability_metric': company.profitability_metric or 'EBITDA',
            'snapshots': []
        }

        for cf in cash_flows:
            snapshot = {
                'date': cf.note.created_at.isoformat(),
                'note_id': cf.note.pk,
                'note_title': cf.note.title[:50],
                'fcf': [
                    float(cf.fcf_year_1) if cf.fcf_year_1 else None,
                    float(cf.fcf_year_2) if cf.fcf_year_2 else None,
                    float(cf.fcf_year_3) if cf.fcf_year_3 else None,
                    float(cf.fcf_year_4) if cf.fcf_year_4 else None,
                    float(cf.fcf_year_5) if cf.fcf_year_5 else None,
                ],
                'terminal_value': float(cf.terminal_value) if cf.terminal_value else None,
                'irr': float(cf.calculated_irr) if cf.calculated_irr else None,
                'price': float(cf.current_price) if cf.current_price else None,
            }

            # Add revenue if any values exist
            if any([cf.revenue_year_1, cf.revenue_year_2, cf.revenue_year_3,
                    cf.revenue_year_4, cf.revenue_year_5]):
                snapshot['revenue'] = [
                    float(cf.revenue_year_1) if cf.revenue_year_1 else None,
                    float(cf.revenue_year_2) if cf.revenue_year_2 else None,
                    float(cf.revenue_year_3) if cf.revenue_year_3 else None,
                    float(cf.revenue_year_4) if cf.revenue_year_4 else None,
                    float(cf.revenue_year_5) if cf.revenue_year_5 else None,
                ]
            else:
                snapshot['revenue'] = None

            # Add EBIT/EBITDA if any values exist
            if any([cf.ebit_ebitda_year_1, cf.ebit_ebitda_year_2, cf.ebit_ebitda_year_3,
                    cf.ebit_ebitda_year_4, cf.ebit_ebitda_year_5]):
                snapshot['ebit_ebitda'] = [
                    float(cf.ebit_ebitda_year_1) if cf.ebit_ebitda_year_1 else None,
                    float(cf.ebit_ebitda_year_2) if cf.ebit_ebitda_year_2 else None,
                    float(cf.ebit_ebitda_year_3) if cf.ebit_ebitda_year_3 else None,
                    float(cf.ebit_ebitda_year_4) if cf.ebit_ebitda_year_4 else None,
                    float(cf.ebit_ebitda_year_5) if cf.ebit_ebitda_year_5 else None,
                ]
            else:
                snapshot['ebit_ebitda'] = None

            data['snapshots'].append(snapshot)

        return JsonResponse(data)
