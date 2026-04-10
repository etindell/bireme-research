"""
Views for Portfolio management.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.generic import ListView, DetailView, CreateView, View

from core.mixins import OrganizationViewMixin
from .forms import PortfolioSnapshotForm
from .models import PortfolioSnapshot, PortfolioPosition
from .services import (
    extract_portfolio_from_file,
    match_positions_to_companies,
    calculate_portfolio_irr_from_weights,
    estimate_portfolio_volatility,
)

logger = logging.getLogger(__name__)


def _build_summary_context(snapshot):
    """Build common context dict for the portfolio summary partial."""
    positions = snapshot.positions.all()
    current_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=False)
    proposed_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=True)
    current_weight_sum = sum(float(p.current_weight) for p in positions) * 100
    proposed_weight_sum = sum(float(p.proposed_weight if p.proposed_weight is not None else p.current_weight) for p in positions) * 100

    # Note: IRR values from CompanyValuation.calculated_irr are already
    # stored as percentages (e.g. 15.0 = 15%), so no conversion needed.
    return {
        'snapshot': snapshot,
        'positions': positions,
        'current_irr': current_irr,
        'proposed_irr': proposed_irr,
        'current_weight_sum': current_weight_sum,
        'proposed_weight_sum': proposed_weight_sum,
    }


def _run_extraction(snapshot, organization):
    """
    Run Gemini extraction on a snapshot's source file, match companies, and create positions.
    Returns (success: bool, message: str).
    """
    try:
        file_path = snapshot.source_file.path
    except Exception as e:
        snapshot.extraction_raw = _error_dict('file_path_error',
            'Could not locate the uploaded file on disk.', str(e))
        snapshot.save(update_fields=['extraction_raw'])
        return False, str(e)

    try:
        extracted, error = extract_portfolio_from_file(file_path)
    except Exception as e:
        snapshot.extraction_raw = _error_dict('unexpected_error',
            'An unexpected error occurred during extraction.', str(e))
        snapshot.save(update_fields=['extraction_raw'])
        return False, str(e)

    if error:
        snapshot.extraction_raw = _error_dict(error.code, error.message, error.detail)
        snapshot.save(update_fields=['extraction_raw'])
        return False, str(error)

    snapshot.extraction_raw = {'positions': extracted}

    try:
        matched = match_positions_to_companies(extracted, organization)

        for pos in matched:
            weight = Decimal(str(pos.get('weight', 0)))
            irr_val = Decimal(str(pos['irr'])) if pos.get('irr') is not None else None
            PortfolioPosition.objects.create(
                snapshot=snapshot,
                company=pos.get('company'),
                ticker=pos.get('ticker', ''),
                name_extracted=pos.get('name', ''),
                current_weight=weight,
                proposed_weight=weight,
                irr=irr_val,
                irr_source=pos.get('irr_source', 'valuation'),
            )
    except Exception as e:
        snapshot.extraction_raw = _error_dict('matching_error',
            'Positions were extracted but failed during company matching.', str(e))
        snapshot.save(update_fields=['extraction_raw'])
        return False, str(e)

    positions = snapshot.positions.all()
    current_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=False)
    if current_irr is not None:
        snapshot.total_irr = Decimal(str(round(current_irr, 4)))

    snapshot.save()

    matched_count = sum(1 for p in matched if p.get('company'))
    return True, f'Extracted {len(matched)} positions ({matched_count} matched to existing companies).'


def _error_dict(code, message, detail=''):
    return {
        'error': True,
        'error_code': code,
        'error_message': message,
        'error_detail': detail,
    }


class PortfolioListView(OrganizationViewMixin, ListView):
    model = PortfolioSnapshot
    template_name = 'portfolio/list.html'
    context_object_name = 'snapshots'
    ordering = ['-as_of_date', '-created_at']


class PortfolioCreateView(OrganizationViewMixin, CreateView):
    model = PortfolioSnapshot
    form_class = PortfolioSnapshotForm
    template_name = 'portfolio/create.html'

    def form_valid(self, form):
        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        success, msg = _run_extraction(self.object, self.request.organization)
        if success:
            messages.success(self.request, msg)
        else:
            messages.error(self.request, f'Extraction failed: {msg}')

        return response

    def get_success_url(self):
        return reverse('portfolio:detail', kwargs={'pk': self.object.pk})


class PortfolioReExtractView(OrganizationViewMixin, View):
    """Re-run extraction on an existing snapshot's source file."""
    model = PortfolioSnapshot

    def post(self, request, pk):
        snapshot = get_object_or_404(
            PortfolioSnapshot.objects.filter(organization=request.organization),
            pk=pk,
        )

        # Clear existing positions
        snapshot.positions.all().delete()
        snapshot.total_irr = None
        snapshot.total_volatility = None

        success, msg = _run_extraction(snapshot, request.organization)
        if success:
            messages.success(request, msg)
        else:
            messages.error(request, f'Extraction failed: {msg}')

        return redirect('portfolio:detail', pk=snapshot.pk)


class PortfolioSetDefaultIRRView(OrganizationViewMixin, View):
    """Set a default IRR for all positions that don't have one."""
    model = PortfolioSnapshot

    def post(self, request, pk):
        snapshot = get_object_or_404(
            PortfolioSnapshot.objects.filter(organization=request.organization),
            pk=pk,
        )

        irr_str = request.POST.get('default_irr', '').strip()
        try:
            default_irr = Decimal(irr_str)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid IRR value.')
            return redirect('portfolio:detail', pk=pk)

        # Apply to positions without an IRR
        updated = snapshot.positions.filter(irr__isnull=True).update(
            irr=default_irr,
            irr_source='manual',
        )

        if updated:
            messages.success(request, f'Set {default_irr}% IRR on {updated} position(s).')
        else:
            messages.info(request, 'All positions already have an IRR.')

        return redirect('portfolio:detail', pk=pk)


class PortfolioAddPositionView(OrganizationViewMixin, View):
    """Add a position from an existing company in the database."""
    model = PortfolioSnapshot

    def post(self, request, pk):
        from apps.companies.models import Company

        snapshot = get_object_or_404(
            PortfolioSnapshot.objects.filter(organization=request.organization),
            pk=pk,
        )

        company_id = request.POST.get('company_id', '').strip()
        weight_str = request.POST.get('weight', '').strip()

        if not company_id:
            messages.error(request, 'Please select a company.')
            return redirect('portfolio:detail', pk=pk)

        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            pk=company_id,
        )

        try:
            weight = Decimal(weight_str) / 100 if weight_str else Decimal('0')
        except (InvalidOperation, ValueError):
            weight = Decimal('0')

        # Get ticker
        primary_ticker = company.tickers.filter(is_primary=True).first()
        ticker = primary_ticker.symbol if primary_ticker else company.tickers.first().symbol if company.tickers.exists() else ''

        # Get IRR from active valuation
        irr = None
        irr_source = 'valuation'
        active_val = company.valuations.filter(is_active=True, is_deleted=False).first()
        if active_val and active_val.calculated_irr is not None:
            irr = active_val.calculated_irr

        PortfolioPosition.objects.create(
            snapshot=snapshot,
            company=company,
            ticker=ticker,
            name_extracted=company.name,
            current_weight=weight,
            proposed_weight=weight,
            irr=irr,
            irr_source=irr_source,
        )

        messages.success(request, f'Added {company.name} ({ticker}).')
        return redirect('portfolio:detail', pk=pk)


class PortfolioDetailView(OrganizationViewMixin, DetailView):
    model = PortfolioSnapshot
    template_name = 'portfolio/detail.html'
    context_object_name = 'snapshot'

    def get_context_data(self, **kwargs):
        from apps.companies.models import Company

        ctx = super().get_context_data(**kwargs)
        ctx.update(_build_summary_context(self.object))
        ctx['companies'] = Company.objects.filter(
            organization=self.request.organization,
        ).order_by('name')
        return ctx


class PortfolioUpdateWeightView(OrganizationViewMixin, View):
    """Update a single position's proposed weight and reload the page."""
    model = PortfolioSnapshot

    def post(self, request, pk, position_pk):
        snapshot = get_object_or_404(
            PortfolioSnapshot.objects.filter(organization=request.organization),
            pk=pk,
        )
        position = get_object_or_404(snapshot.positions, pk=position_pk)

        weight_str = request.POST.get('proposed_weight', '').strip()
        try:
            weight_pct = Decimal(weight_str)
            position.proposed_weight = weight_pct / 100
            position.save(update_fields=['proposed_weight'])
        except (InvalidOperation, ValueError):
            pass

        return redirect('portfolio:detail', pk=pk)


class PortfolioRecalculateView(OrganizationViewMixin, View):
    """HTMX endpoint that recalculates all portfolio-level metrics."""
    model = PortfolioSnapshot

    def post(self, request, pk):
        snapshot = get_object_or_404(
            PortfolioSnapshot.objects.filter(organization=request.organization),
            pk=pk,
        )

        positions = snapshot.positions.all()
        proposed_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=True)
        if proposed_irr is not None:
            snapshot.total_irr = Decimal(str(round(proposed_irr, 4)))
            snapshot.save(update_fields=['total_irr'])

        ctx = _build_summary_context(snapshot)
        html = render_to_string('portfolio/partials/portfolio_summary.html', ctx, request=request)
        return HttpResponse(html)


class PortfolioVolatilityView(OrganizationViewMixin, View):
    """HTMX endpoint that fetches/refreshes volatility data."""
    model = PortfolioSnapshot

    def post(self, request, pk):
        snapshot = get_object_or_404(
            PortfolioSnapshot.objects.filter(organization=request.organization),
            pk=pk,
        )
        positions = list(snapshot.positions.all())
        vol_data = estimate_portfolio_volatility(positions)

        # Convert to percentages for display
        if vol_data.get('portfolio_volatility') is not None:
            raw_vol = vol_data['portfolio_volatility']
            snapshot.total_volatility = Decimal(str(round(raw_vol, 4)))
            snapshot.save(update_fields=['total_volatility'])
            vol_data['portfolio_volatility'] = raw_vol * 100

        vol_data['individual_volatilities'] = {
            k: v * 100 for k, v in vol_data.get('individual_volatilities', {}).items()
        }

        html = render_to_string('portfolio/partials/volatility_panel.html', {
            'vol_data': vol_data,
            'snapshot': snapshot,
        }, request=request)
        return HttpResponse(html)
