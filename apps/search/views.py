"""
Global search views.
"""
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.search import SearchQuery, SearchRank

from apps.companies.models import Company
from apps.notes.models import Note


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    """
    Global search across companies and notes.
    Supports HTMX partial responses for live search.
    """
    template_name = 'search/search.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip()

        context['query'] = query
        context['companies'] = []
        context['notes'] = []
        context['has_results'] = False

        if query and len(query) >= 2 and hasattr(self.request, 'organization') and self.request.organization:
            search_query = SearchQuery(query, search_type='websearch')

            # Search companies
            companies = Company.objects.filter(
                organization=self.request.organization
            ).annotate(
                rank=SearchRank('search_vector', search_query)
            ).filter(
                search_vector=search_query
            ).order_by('-rank')[:10]

            # Search notes
            notes = Note.objects.filter(
                organization=self.request.organization
            ).annotate(
                rank=SearchRank('search_vector', search_query)
            ).filter(
                search_vector=search_query
            ).select_related(
                'company', 'note_type', 'created_by'
            ).order_by('-rank')[:20]

            context['companies'] = companies
            context['notes'] = notes
            context['has_results'] = companies.exists() or notes.exists()

        return context

    def get_template_names(self):
        # Only return partial for targeted HTMX requests (not boosted navigation)
        if self.request.htmx and not self.request.htmx.boosted:
            return ['search/partials/search_results.html']
        return [self.template_name]
