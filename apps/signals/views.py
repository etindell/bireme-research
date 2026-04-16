"""
Views for the Signals app.
"""
from datetime import timedelta

from django.db.models import Count, Q, Min, Max
from django.db.models.functions import TruncMonth
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView

from core.mixins import OrganizationViewMixin
from apps.companies.models import Company
from apps.signals.models import (
    CertificateSubdomainObservation,
    SignalSourceConfig,
    SignalSyncRun,
)


class SignalIndexView(OrganizationViewMixin, ListView):
    """List all enabled signal configs for the current organization."""
    model = SignalSourceConfig
    template_name = 'signals/index.html'
    context_object_name = 'configs'

    def get_queryset(self):
        return super().get_queryset().filter(
            is_enabled=True,
        ).select_related('company')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        d30 = now - timedelta(days=30)
        d90 = now - timedelta(days=90)

        config_stats = []
        for config in ctx['configs']:
            candidates = CertificateSubdomainObservation.objects.filter(
                config=config,
                tenant_candidate=True,
                is_excluded=False,
            )
            total = candidates.count()
            new_30d = candidates.filter(first_seen_at__gte=d30).count()
            new_90d = candidates.filter(first_seen_at__gte=d90).count()
            latest_first_seen = candidates.aggregate(
                latest=Max('first_seen_at')
            )['latest']

            config_stats.append({
                'config': config,
                'total_candidates': total,
                'new_30d': new_30d,
                'new_90d': new_90d,
                'latest_first_seen': latest_first_seen,
            })

        ctx['config_stats'] = config_stats
        return ctx


class CompanySignalDetailView(OrganizationViewMixin, DetailView):
    """Detail page for a company's signal data."""
    model = SignalSourceConfig
    template_name = 'signals/company_detail.html'
    context_object_name = 'config'

    def get_object(self, queryset=None):
        qs = self.get_queryset().select_related('company')
        return get_object_or_404(
            qs,
            company__slug=self.kwargs['company_slug'],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        config = self.object
        now = timezone.now()
        d30 = now - timedelta(days=30)
        d90 = now - timedelta(days=90)

        candidates = CertificateSubdomainObservation.objects.filter(
            config=config,
            tenant_candidate=True,
            is_excluded=False,
        )
        all_observations = CertificateSubdomainObservation.objects.filter(
            config=config,
        )

        # Summary stats
        ctx['total_candidates'] = candidates.count()
        ctx['new_30d'] = candidates.filter(first_seen_at__gte=d30).count()
        ctx['new_90d'] = candidates.filter(first_seen_at__gte=d90).count()
        ctx['total_excluded'] = all_observations.filter(
            Q(is_excluded=True) | Q(tenant_candidate=False)
        ).count()

        # Last successful sync
        ctx['last_sync'] = SignalSyncRun.objects.filter(
            config=config,
            status=SignalSyncRun.Status.SUCCESS,
        ).first()

        # Monthly trend
        monthly = (
            candidates
            .annotate(month=TruncMonth('first_seen_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        cumulative = 0
        monthly_trend = []
        for row in monthly:
            cumulative += row['count']
            monthly_trend.append({
                'month': row['month'],
                'new_count': row['count'],
                'cumulative': cumulative,
            })
        ctx['monthly_trend'] = monthly_trend
        ctx['monthly_max'] = max((r['new_count'] for r in monthly_trend), default=1)

        # Recent candidate observations
        ctx['recent_candidates'] = candidates.order_by('-first_seen_at')[:100]

        # Non-candidate / excluded observations
        ctx['other_observations'] = all_observations.filter(
            Q(is_excluded=True) | Q(tenant_candidate=False)
        ).order_by('-first_seen_at')[:100]

        ctx['company'] = config.company
        return ctx


class SyncSignalView(OrganizationViewMixin, View):
    """Trigger a sync for a company's signal config."""
    model = SignalSourceConfig

    def get_queryset(self):
        qs = SignalSourceConfig.objects.all()
        if hasattr(self.request, 'organization') and self.request.organization:
            return qs.filter(organization=self.request.organization)
        return qs.none()

    def post(self, request, company_slug):
        config = get_object_or_404(
            self.get_queryset().select_related('company'),
            company__slug=company_slug,
        )

        from apps.signals.services.cybozu_ct import run_sync
        run_sync(config)

        # If HTMX request, return a redirect header for client-side redirect
        if request.htmx:
            response = HttpResponseRedirect(
                reverse('signals:company_detail', kwargs={'company_slug': company_slug})
            )
            response['HX-Redirect'] = response['Location']
            return response

        return HttpResponseRedirect(
            reverse('signals:company_detail', kwargs={'company_slug': company_slug})
        )


class ExcludeObservationView(OrganizationViewMixin, View):
    """Mark an observation as excluded."""
    model = SignalSourceConfig

    def get_queryset(self):
        qs = SignalSourceConfig.objects.all()
        if hasattr(self.request, 'organization') and self.request.organization:
            return qs.filter(organization=self.request.organization)
        return qs.none()

    def post(self, request, pk):
        obs = get_object_or_404(
            CertificateSubdomainObservation.objects.filter(
                config__in=self.get_queryset()
            ),
            pk=pk,
        )
        obs.is_excluded = True
        obs.exclude_reason = request.POST.get('reason', 'Manually excluded')
        obs.save(update_fields=['is_excluded', 'exclude_reason'])

        if request.htmx:
            return _render_obs_row(request, obs)

        return HttpResponseRedirect(
            reverse('signals:company_detail',
                    kwargs={'company_slug': obs.company.slug})
        )


class IncludeObservationView(OrganizationViewMixin, View):
    """Un-exclude an observation."""
    model = SignalSourceConfig

    def get_queryset(self):
        qs = SignalSourceConfig.objects.all()
        if hasattr(self.request, 'organization') and self.request.organization:
            return qs.filter(organization=self.request.organization)
        return qs.none()

    def post(self, request, pk):
        obs = get_object_or_404(
            CertificateSubdomainObservation.objects.filter(
                config__in=self.get_queryset()
            ),
            pk=pk,
        )
        obs.is_excluded = False
        obs.exclude_reason = ''
        obs.save(update_fields=['is_excluded', 'exclude_reason'])

        if request.htmx:
            return _render_obs_row(request, obs)

        return HttpResponseRedirect(
            reverse('signals:company_detail',
                    kwargs={'company_slug': obs.company.slug})
        )


class CompanySignalCardView(OrganizationViewMixin, View):
    """
    Returns the signal card partial for the company detail page.
    Used via HTMX or template include.
    """
    model = SignalSourceConfig

    def get_queryset(self):
        qs = SignalSourceConfig.objects.all()
        if hasattr(self.request, 'organization') and self.request.organization:
            return qs.filter(organization=self.request.organization)
        return qs.none()

    def get(self, request, company_slug):
        from django.template.loader import render_to_string
        from django.http import HttpResponse

        config = self.get_queryset().filter(
            company__slug=company_slug,
        ).select_related('company').first()

        now = timezone.now()
        d30 = now - timedelta(days=30)

        context = {'company_slug': company_slug}

        if config:
            candidates = CertificateSubdomainObservation.objects.filter(
                config=config,
                tenant_candidate=True,
                is_excluded=False,
            )
            context['config'] = config
            context['total_candidates'] = candidates.count()
            context['new_30d'] = candidates.filter(first_seen_at__gte=d30).count()
            context['last_synced_at'] = config.last_synced_at

        html = render_to_string(
            'signals/partials/company_card.html',
            context,
            request=request,
        )
        return HttpResponse(html)


def _render_obs_row(request, obs):
    """Render a single observation row partial for HTMX swap."""
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    html = render_to_string(
        'signals/partials/observation_row.html',
        {'obs': obs},
        request=request,
    )
    return HttpResponse(html)
