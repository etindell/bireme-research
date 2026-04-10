"""
Views for Portfolio management.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
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


def _build_summary_context(snapshot):
    """Build common context dict for the portfolio summary partial."""
    positions = snapshot.positions.all()
    current_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=False)
    proposed_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=True)
    current_weight_sum = sum(float(p.current_weight) for p in positions) * 100
    proposed_weight_sum = sum(float(p.proposed_weight if p.proposed_weight is not None else p.current_weight) for p in positions) * 100

    return {
        'snapshot': snapshot,
        'positions': positions,
        'current_irr': current_irr * 100 if current_irr is not None else None,
        'proposed_irr': proposed_irr * 100 if proposed_irr is not None else None,
        'current_weight_sum': current_weight_sum,
        'proposed_weight_sum': proposed_weight_sum,
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

    def _save_extraction_error(self, snapshot, code, message, detail=''):
        """Persist an extraction error on the snapshot for display on the detail page."""
        snapshot.extraction_raw = {
            'error': True,
            'error_code': code,
            'error_message': message,
            'error_detail': detail,
        }
        snapshot.save(update_fields=['extraction_raw'])

    def form_valid(self, form):
        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        snapshot = self.object

        try:
            file_path = snapshot.source_file.path
        except Exception as e:
            self._save_extraction_error(snapshot, 'file_path_error',
                'Could not locate the uploaded file on disk.', str(e))
            return response

        try:
            extracted, error = extract_portfolio_from_file(file_path)
        except Exception as e:
            self._save_extraction_error(snapshot, 'unexpected_error',
                'An unexpected error occurred during extraction.', str(e))
            return response

        if error:
            self._save_extraction_error(snapshot, error.code, error.message, error.detail)
            return response

        snapshot.extraction_raw = {'positions': extracted}

        try:
            matched = match_positions_to_companies(extracted, self.request.organization)

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
            self._save_extraction_error(snapshot, 'matching_error',
                'Positions were extracted but failed during company matching.', str(e))
            return response

        positions = snapshot.positions.all()
        current_irr = calculate_portfolio_irr_from_weights(positions, use_proposed=False)
        if current_irr is not None:
            snapshot.total_irr = Decimal(str(round(current_irr, 4)))

        snapshot.save()

        matched_count = sum(1 for p in matched if p.get('company'))
        messages.success(
            self.request,
            f'Extracted {len(matched)} positions ({matched_count} matched to existing companies).'
        )
        return response

    def get_success_url(self):
        return reverse('portfolio:detail', kwargs={'pk': self.object.pk})


class PortfolioDetailView(OrganizationViewMixin, DetailView):
    model = PortfolioSnapshot
    template_name = 'portfolio/detail.html'
    context_object_name = 'snapshot'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_build_summary_context(self.object))
        return ctx


class PortfolioUpdateWeightView(OrganizationViewMixin, View):
    """HTMX endpoint to update a single position's proposed weight."""
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

        ctx = _build_summary_context(snapshot)
        html = render_to_string('portfolio/partials/portfolio_summary.html', ctx, request=request)
        return HttpResponse(html)


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
