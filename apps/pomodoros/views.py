"""
Views for pomodoro timer.
"""
import json
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .forms import PomodoroStartForm
from .models import Pomodoro


class PomodoroPageView(LoginRequiredMixin, TemplateView):
    """Main pomodoro timer page."""
    template_name = 'pomodoros/pomodoro_timer.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.request.organization

        # Check for an active (incomplete) pomodoro to resume
        active_pomodoro = Pomodoro.objects.filter(
            organization=org,
            user=self.request.user,
            is_completed=False,
        ).order_by('-started_at').first()

        # If active pomodoro has expired, don't treat as active timer
        # but show completion prompt
        if active_pomodoro:
            if active_pomodoro.seconds_remaining <= 0:
                context['expired_pomodoro'] = active_pomodoro
                active_pomodoro = None

        context['active_pomodoro'] = active_pomodoro
        context['form'] = PomodoroStartForm(organization=org)
        context['todays_count'] = Pomodoro.objects.filter(
            organization=org,
            user=self.request.user,
            is_completed=True,
        ).today().count()

        return context


class PomodoroStartView(LoginRequiredMixin, View):
    """Start a new pomodoro. Returns timer partial."""

    def post(self, request):
        org = request.organization
        form = PomodoroStartForm(request.POST, organization=org)

        # Cancel any existing incomplete pomodoros
        Pomodoro.objects.filter(
            organization=org,
            user=request.user,
            is_completed=False,
        ).delete()

        if form.is_valid():
            company = form.cleaned_data.get('company')
            topic_label = company.name if company else 'All Other'

            pomodoro = Pomodoro.objects.create(
                organization=org,
                user=request.user,
                company=company,
                topic_label=topic_label,
                started_at=timezone.now(),
                created_by=request.user,
            )

            html = render_to_string('pomodoros/partials/timer_display.html', {
                'pomodoro': pomodoro,
            }, request=request)
            return HttpResponse(html)

        # Form invalid - return the form with errors
        html = render_to_string('pomodoros/partials/start_form.html', {
            'form': form,
        }, request=request)
        return HttpResponse(html)


class PomodoroCompleteView(LoginRequiredMixin, View):
    """Mark pomodoro complete. Returns focus prompt partial."""

    def post(self, request, pk):
        pomodoro = get_object_or_404(
            Pomodoro,
            pk=pk,
            organization=request.organization,
            user=request.user,
        )
        pomodoro.mark_complete()

        html = render_to_string('pomodoros/partials/completion_prompt.html', {
            'pomodoro': pomodoro,
        }, request=request)
        return HttpResponse(html)


class PomodoroFocusResponseView(LoginRequiredMixin, View):
    """Record focus response. Returns reset form partial."""

    def post(self, request, pk):
        pomodoro = get_object_or_404(
            Pomodoro,
            pk=pk,
            organization=request.organization,
            user=request.user,
        )
        was_focused = request.POST.get('was_focused') == 'true'
        pomodoro.set_focus_response(was_focused)

        todays_count = Pomodoro.objects.filter(
            organization=request.organization,
            user=request.user,
            is_completed=True,
        ).today().count()

        form = PomodoroStartForm(organization=request.organization)
        html = render_to_string('pomodoros/partials/timer_reset.html', {
            'pomodoro': pomodoro,
            'form': form,
            'todays_count': todays_count,
        }, request=request)
        response = HttpResponse(html)
        response['HX-Trigger'] = json.dumps({
            'pomodoroCompleted': {'count': todays_count}
        })
        return response


class PomodoroCancelView(LoginRequiredMixin, View):
    """Cancel/delete an incomplete pomodoro."""

    def post(self, request, pk):
        pomodoro = get_object_or_404(
            Pomodoro,
            pk=pk,
            organization=request.organization,
            user=request.user,
            is_completed=False,
        )
        pomodoro.delete()

        form = PomodoroStartForm(organization=request.organization)
        html = render_to_string('pomodoros/partials/start_form.html', {
            'form': form,
        }, request=request)
        return HttpResponse(html)


class PomodoroWeeklyDataView(LoginRequiredMixin, View):
    """JSON API for weekly chart data."""

    def get(self, request):
        org = request.organization
        week_offset = int(request.GET.get('week_offset', 0))

        now = timezone.now()
        # Monday of current week
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Apply offset
        monday = monday + timedelta(weeks=week_offset)
        sunday = monday + timedelta(days=7)

        pomodoros = Pomodoro.objects.filter(
            organization=org,
            user=request.user,
            is_completed=True,
            started_at__gte=monday,
            started_at__lt=sunday,
        ).values('started_at', 'was_focused', 'topic_label')

        # Build per-day data
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        focused = [0] * 7
        distracted = [0] * 7
        topics = {}

        for p in pomodoros:
            day_idx = p['started_at'].weekday()
            if p['was_focused'] is True:
                focused[day_idx] += 1
            elif p['was_focused'] is False:
                distracted[day_idx] += 1
            else:
                # No response recorded - count as focused
                focused[day_idx] += 1

            label = p['topic_label']
            topics[label] = topics.get(label, 0) + 1

        # Week label
        week_label = f"{monday.strftime('%b %d')} - {(sunday - timedelta(days=1)).strftime('%b %d, %Y')}"

        return JsonResponse({
            'days': days,
            'focused': focused,
            'distracted': distracted,
            'topics': topics,
            'week_label': week_label,
            'week_offset': week_offset,
            'total': sum(focused) + sum(distracted),
        })
