"""
Core views including dashboard.
"""
import json
from datetime import timedelta
from collections import defaultdict

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, Length
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

from apps.companies.models import Company
from apps.notes.models import Note
from apps.todos.models import Todo


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

            # Pending todos
            context['pending_todos'] = Todo.objects.filter(
                organization=org,
                is_completed=False
            ).select_related('company', 'category').order_by('-created_at')[:5]

        return context


class ActivityDataView(LoginRequiredMixin, View):
    """API endpoint for activity chart data."""

    def get(self, request):
        if not hasattr(request, 'organization') or not request.organization:
            return JsonResponse({'error': 'No organization'}, status=400)

        org = request.organization
        period = request.GET.get('period', 'day')  # day, week, month

        # Determine date range and truncation function
        now = timezone.now()
        if period == 'day':
            start_date = now - timedelta(days=30)
            trunc_func = TruncDate
            date_format = '%Y-%m-%d'
        elif period == 'week':
            start_date = now - timedelta(weeks=12)
            trunc_func = TruncWeek
            date_format = '%Y-%m-%d'
        else:  # month
            start_date = now - timedelta(days=365)
            trunc_func = TruncMonth
            date_format = '%Y-%m'

        # Get notes data with word counts
        notes_data = Note.objects.filter(
            organization=org,
            created_at__gte=start_date
        ).annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')

        # Calculate word counts per period
        notes_with_words = Note.objects.filter(
            organization=org,
            created_at__gte=start_date
        ).annotate(
            period=trunc_func('created_at')
        ).values('period', 'title', 'content')

        word_counts = defaultdict(int)
        for note in notes_with_words:
            period_key = note['period'].strftime(date_format) if note['period'] else None
            if period_key:
                title_words = len((note['title'] or '').split())
                content_words = len((note['content'] or '').split())
                word_counts[period_key] += title_words + content_words

        # Get new companies data (all statuses, not just watchlist)
        companies_data = Company.objects.filter(
            organization=org,
            created_at__gte=start_date
        ).annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')

        # Build response data
        labels = []
        notes_counts = []
        words_counts = []
        companies_counts = []

        # Create lookup dictionaries
        notes_lookup = {
            item['period'].strftime(date_format): item['count']
            for item in notes_data if item['period']
        }
        companies_lookup = {
            item['period'].strftime(date_format): item['count']
            for item in companies_data if item['period']
        }

        # Generate all periods in range
        current = start_date
        while current <= now:
            if period == 'day':
                period_key = current.strftime(date_format)
                label = current.strftime('%b %d')
                current += timedelta(days=1)
            elif period == 'week':
                period_key = current.strftime(date_format)
                label = current.strftime('%b %d')
                current += timedelta(weeks=1)
            else:  # month
                period_key = current.strftime(date_format)
                label = current.strftime('%b %Y')
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    current = current.replace(month=current.month + 1, day=1)

            labels.append(label)
            notes_counts.append(notes_lookup.get(period_key, 0))
            words_counts.append(word_counts.get(period_key, 0))
            companies_counts.append(companies_lookup.get(period_key, 0))

        return JsonResponse({
            'labels': labels,
            'notes': notes_counts,
            'words': words_counts,
            'companies': companies_counts,
            'totals': {
                'notes': sum(notes_counts),
                'words': sum(words_counts),
                'companies': sum(companies_counts),
            }
        })
