"""
Core views including dashboard.
"""
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from apps.companies.models import Company
from apps.notes.models import Note


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view."""
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if hasattr(self.request, 'organization') and self.request.organization:
            org = self.request.organization

            # Pipeline counts
            context['portfolio_count'] = Company.objects.filter(
                organization=org, status=Company.Status.PORTFOLIO
            ).count()
            context['on_deck_count'] = Company.objects.filter(
                organization=org, status=Company.Status.ON_DECK
            ).count()
            context['watchlist_count'] = Company.objects.filter(
                organization=org, status=Company.Status.WATCHLIST
            ).count()
            context['notes_count'] = Note.objects.filter(organization=org).count()

            # Recent activity
            context['recent_notes'] = Note.objects.filter(
                organization=org
            ).select_related(
                'company', 'note_type'
            ).order_by('-created_at')[:5]

            context['recent_companies'] = Company.objects.filter(
                organization=org
            ).prefetch_related('tickers').order_by('-updated_at')[:5]

        return context
