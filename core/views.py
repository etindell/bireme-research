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
            now = timezone.now()

            # Pipeline counts
            context['long_book_count'] = Company.objects.filter(
                organization=org, status=Company.Status.LONG_BOOK
            ).count()
            context['short_book_count'] = Company.objects.filter(
                organization=org, status=Company.Status.SHORT_BOOK
            ).count()
            context['on_deck_count'] = Company.objects.filter(
                organization=org, status=Company.Status.ON_DECK
            ).count()
            context['watchlist_count'] = Company.objects.filter(
                organization=org, status=Company.Status.WATCHLIST
            ).count()
            # Exclude imported notes from stats
            context['notes_count'] = Note.objects.filter(
                organization=org,
                is_imported=False
            ).count()

            # Todo completion stats
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())

            context['todos_completed_today'] = Todo.objects.filter(
                organization=org,
                is_completed=True,
                completed_at__gte=today_start
            ).count()
            context['todos_completed_this_week'] = Todo.objects.filter(
                organization=org,
                is_completed=True,
                completed_at__gte=week_start
            ).count()
            context['todos_pending_count'] = Todo.objects.filter(
                organization=org,
                is_completed=False
            ).count()

            # Recent activity (exclude imported notes)
            context['recent_notes'] = Note.objects.filter(
                organization=org,
                is_imported=False
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


class FixImportedNotesView(LoginRequiredMixin, View):
    """Admin endpoint to check and fix imported notes flags."""

    def get(self, request):
        if not request.user.is_staff:
            return JsonResponse({'error': 'Admin only'}, status=403)

        # Get stats
        total = Note.objects.count()
        imported_true = Note.objects.filter(is_imported=True).count()
        imported_false = Note.objects.filter(is_imported=False).count()
        with_written_at = Note.objects.filter(written_at__isnull=False).count()

        # Find notes that should be marked as imported (have written_at but is_imported=False)
        missed = Note.objects.filter(written_at__isnull=False, is_imported=False).count()

        # Check if fix parameter is present
        if request.GET.get('fix') == 'true':
            updated = Note.objects.filter(
                written_at__isnull=False,
                is_imported=False
            ).update(is_imported=True)
            return JsonResponse({
                'status': 'fixed',
                'updated': updated,
                'message': f'Marked {updated} notes as imported'
            })

        return JsonResponse({
            'total_notes': total,
            'is_imported_true': imported_true,
            'is_imported_false': imported_false,
            'has_written_at': with_written_at,
            'needs_fix': missed,
            'message': f'{missed} notes have written_at but is_imported=False. Add ?fix=true to fix.'
        })


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

        # Get notes data with word counts (exclude imported notes)
        notes_data = Note.objects.filter(
            organization=org,
            created_at__gte=start_date,
            is_imported=False
        ).annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')

        # Calculate word counts per period (exclude imported notes)
        notes_with_words = Note.objects.filter(
            organization=org,
            created_at__gte=start_date,
            is_imported=False
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

        # Get todos completed data
        todos_data = Todo.objects.filter(
            organization=org,
            is_completed=True,
            completed_at__gte=start_date
        ).annotate(
            period=trunc_func('completed_at')
        ).values('period').annotate(
            count=Count('id')
        ).order_by('period')

        # Build response data
        labels = []
        notes_counts = []
        words_counts = []
        companies_counts = []
        todos_counts = []

        # Create lookup dictionaries
        notes_lookup = {
            item['period'].strftime(date_format): item['count']
            for item in notes_data if item['period']
        }
        companies_lookup = {
            item['period'].strftime(date_format): item['count']
            for item in companies_data if item['period']
        }
        todos_lookup = {
            item['period'].strftime(date_format): item['count']
            for item in todos_data if item['period']
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
            todos_counts.append(todos_lookup.get(period_key, 0))

        return JsonResponse({
            'labels': labels,
            'notes': notes_counts,
            'words': words_counts,
            'companies': companies_counts,
            'todos': todos_counts,
            'totals': {
                'notes': sum(notes_counts),
                'words': sum(words_counts),
                'companies': sum(companies_counts),
                'todos': sum(todos_counts),
            }
        })
