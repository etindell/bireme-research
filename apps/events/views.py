"""
Views for events app - event management, guest tracking, and RSVP.
"""
import json

from django.contrib import messages
from django.core.mail import send_mail
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, TemplateView

from core.mixins import OrganizationViewMixin

from .forms import EventForm, ScreenshotUploadForm, GuestForm, RsvpForm
from .models import Event, Guest, GuestScreenshot
from .services import extract_guests_from_screenshot, generate_invitation_email


# --- Authenticated views ---

class EventListView(OrganizationViewMixin, ListView):
    model = Event
    template_name = 'events/event_list.html'
    context_object_name = 'events'


class EventCreateView(OrganizationViewMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = 'events/event_form.html'

    def get_success_url(self):
        return reverse('events:detail', kwargs={'pk': self.object.pk})


class EventDetailView(OrganizationViewMixin, DetailView):
    model = Event
    template_name = 'events/event_detail.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['screenshot_form'] = ScreenshotUploadForm()
        context['guest_form'] = GuestForm()
        context['guests'] = self.object.guests.all()
        return context


class EventUpdateView(OrganizationViewMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'events/event_form.html'

    def get_success_url(self):
        return reverse('events:detail', kwargs={'pk': self.object.pk})


class EventDeleteView(OrganizationViewMixin, DeleteView):
    model = Event
    success_url = reverse_lazy('events:list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete(user=request.user)
        messages.success(request, f'Event "{self.object.name}" deleted.')
        return redirect(self.success_url)


class UploadScreenshotView(OrganizationViewMixin, View):
    """Upload a screenshot and extract guest data via Claude Vision."""

    def get_queryset(self):
        return Event.objects.all()

    def post(self, request, pk):
        event = get_object_or_404(
            Event,
            pk=pk,
            organization=request.organization,
        )
        form = ScreenshotUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, 'Please upload a valid image file.')
            return redirect('events:detail', pk=pk)

        # Save the screenshot
        screenshot = GuestScreenshot.objects.create(
            event=event,
            organization=request.organization,
            image=form.cleaned_data['image'],
            created_by=request.user,
        )

        # Extract guests using Claude Vision
        extracted = extract_guests_from_screenshot(screenshot.image.path)
        screenshot.extracted_data = extracted
        screenshot.is_processed = True
        screenshot.save(update_fields=['extracted_data', 'is_processed'])

        if not extracted:
            messages.warning(request, 'No guest data could be extracted from the screenshot. Try a clearer image.')
            return redirect('events:detail', pk=pk)

        # Return confirmation partial for HTMX, or redirect for regular request
        if request.htmx:
            html = render_to_string('events/partials/confirm_guests.html', {
                'event': event,
                'extracted_guests': extracted,
                'screenshot_id': screenshot.pk,
            }, request=request)
            return HttpResponse(html)

        # Store in session for non-HTMX flow
        request.session[f'extracted_guests_{screenshot.pk}'] = extracted
        return redirect('events:confirm_guests', pk=pk, screenshot_pk=screenshot.pk)


class ConfirmGuestsView(OrganizationViewMixin, View):
    """Review and confirm extracted guests before saving."""

    def get_queryset(self):
        return Event.objects.all()

    def get(self, request, pk, screenshot_pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)
        screenshot = get_object_or_404(GuestScreenshot, pk=screenshot_pk, event=event)

        extracted = screenshot.extracted_data or request.session.get(f'extracted_guests_{screenshot_pk}', [])

        return render_to_string('events/confirm_guests.html', {
            'event': event,
            'extracted_guests': extracted,
            'screenshot_id': screenshot.pk,
        }, request=request)

    def post(self, request, pk, screenshot_pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)

        # Process the confirmed guest list
        names = request.POST.getlist('guest_name')
        emails = request.POST.getlist('guest_email')

        created_count = 0
        skipped_count = 0
        for name, email in zip(names, emails):
            name = name.strip()
            email = email.strip()
            if not name:
                continue
            # Skip duplicates
            if email and Guest.objects.filter(event=event, email=email).exists():
                skipped_count += 1
                continue
            Guest.objects.create(
                event=event,
                organization=request.organization,
                name=name,
                email=email,
                created_by=request.user,
            )
            created_count += 1

        msg = f'{created_count} guest(s) added.'
        if skipped_count:
            msg += f' {skipped_count} duplicate(s) skipped.'
        messages.success(request, msg)

        if request.htmx:
            guests = event.guests.all()
            html = render_to_string('events/partials/guest_list.html', {
                'event': event,
                'guests': guests,
                'guest_form': GuestForm(),
            }, request=request)
            return HttpResponse(html)

        return redirect('events:detail', pk=pk)


class AddGuestView(OrganizationViewMixin, View):
    """Manually add a single guest."""

    def get_queryset(self):
        return Event.objects.all()

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)
        form = GuestForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data['email']
            if Guest.objects.filter(event=event, email=email).exists():
                messages.warning(request, f'A guest with email {email} already exists.')
            else:
                guest = form.save(commit=False)
                guest.event = event
                guest.organization = request.organization
                guest.created_by = request.user
                guest.save()
                messages.success(request, f'{guest.name} added.')

        if request.htmx:
            guests = event.guests.all()
            html = render_to_string('events/partials/guest_list.html', {
                'event': event,
                'guests': guests,
                'guest_form': GuestForm(),
            }, request=request)
            return HttpResponse(html)

        return redirect('events:detail', pk=pk)


class RemoveGuestView(OrganizationViewMixin, View):
    """Remove a guest from an event."""

    def get_queryset(self):
        return Guest.objects.all()

    def post(self, request, pk, guest_pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)
        guest = get_object_or_404(Guest, pk=guest_pk, event=event)
        guest_name = guest.name
        guest.delete(user=request.user)
        messages.success(request, f'{guest_name} removed.')

        if request.htmx:
            guests = event.guests.all()
            html = render_to_string('events/partials/guest_list.html', {
                'event': event,
                'guests': guests,
                'guest_form': GuestForm(),
            }, request=request)
            return HttpResponse(html)

        return redirect('events:detail', pk=pk)


class GenerateEmailsView(OrganizationViewMixin, View):
    """Generate personalized invitation emails for all guests."""

    def get_queryset(self):
        return Event.objects.all()

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)
        guests = event.guests.filter(generated_email='')

        count = 0
        for guest in guests:
            rsvp_url = guest.get_rsvp_url(request)
            email_text = generate_invitation_email(
                guest_name=guest.name,
                event_name=event.name,
                event_date=event.date.strftime('%B %d, %Y at %I:%M %p'),
                event_location=event.location,
                event_description=event.description,
                rsvp_url=rsvp_url,
            )
            guest.generated_email = email_text
            guest.save(update_fields=['generated_email'])
            count += 1

        messages.success(request, f'Generated {count} invitation email(s).')

        if request.htmx:
            guests = event.guests.all()
            html = render_to_string('events/partials/guest_list.html', {
                'event': event,
                'guests': guests,
                'guest_form': GuestForm(),
            }, request=request)
            return HttpResponse(html)

        return redirect('events:detail', pk=pk)


class PreviewEmailView(OrganizationViewMixin, View):
    """Preview a generated email for a guest."""

    def get_queryset(self):
        return Guest.objects.all()

    def get(self, request, pk, guest_pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)
        guest = get_object_or_404(Guest, pk=guest_pk, event=event)

        html = render_to_string('events/partials/email_preview.html', {
            'event': event,
            'guest': guest,
        }, request=request)
        return HttpResponse(html)


class SendEmailsView(OrganizationViewMixin, View):
    """Send invitation emails to all guests with generated emails."""

    def get_queryset(self):
        return Event.objects.all()

    def post(self, request, pk):
        event = get_object_or_404(Event, pk=pk, organization=request.organization)
        guests = event.guests.filter(generated_email__gt='', email_sent=False)

        subject = event.email_subject or f"You're Invited: {event.name}"
        sent_count = 0
        error_count = 0

        for guest in guests:
            if not guest.email:
                continue
            try:
                send_mail(
                    subject=subject,
                    message=guest.generated_email,
                    from_email=None,  # Uses DEFAULT_FROM_EMAIL
                    recipient_list=[guest.email],
                    fail_silently=False,
                )
                guest.email_sent = True
                guest.save(update_fields=['email_sent'])
                sent_count += 1
            except Exception as e:
                error_count += 1

        msg = f'{sent_count} email(s) sent.'
        if error_count:
            msg += f' {error_count} failed.'
        messages.success(request, msg)

        if request.htmx:
            guests = event.guests.all()
            html = render_to_string('events/partials/guest_list.html', {
                'event': event,
                'guests': guests,
                'guest_form': GuestForm(),
            }, request=request)
            return HttpResponse(html)

        return redirect('events:detail', pk=pk)


class RsvpDashboardView(OrganizationViewMixin, DetailView):
    """Dashboard showing RSVP status and food preference breakdown."""
    model = Event
    template_name = 'events/rsvp_dashboard.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        guests = self.object.guests.all()
        context['guests'] = guests

        # Food preference breakdown (only for yes RSVPs)
        yes_guests = guests.filter(rsvp_status='yes')
        food_breakdown = {}
        for choice_value, choice_label in Guest.FOOD_PREFERENCE_CHOICES:
            count = yes_guests.filter(food_preference=choice_value).count()
            if count > 0:
                food_breakdown[choice_label] = count
        context['food_breakdown'] = food_breakdown

        return context


# --- Public RSVP view (no auth required) ---

class RsvpPublicView(View):
    """Public RSVP page - token-based, no authentication required."""

    def get(self, request, token):
        guest = get_object_or_404(Guest.all_objects, rsvp_token=token, is_deleted=False)
        form = RsvpForm(initial={
            'rsvp_status': guest.rsvp_status if guest.rsvp_status != 'pending' else None,
            'food_preference': guest.food_preference,
            'dietary_notes': guest.dietary_notes,
        })
        return HttpResponse(render_to_string('events/rsvp_public.html', {
            'guest': guest,
            'event': guest.event,
            'form': form,
        }, request=request))

    def post(self, request, token):
        guest = get_object_or_404(Guest.all_objects, rsvp_token=token, is_deleted=False)
        form = RsvpForm(request.POST)

        if form.is_valid():
            guest.rsvp_status = form.cleaned_data['rsvp_status']
            if form.cleaned_data.get('food_preference'):
                guest.food_preference = form.cleaned_data['food_preference']
            guest.dietary_notes = form.cleaned_data.get('dietary_notes', '')
            guest.rsvp_responded_at = timezone.now()
            guest.save(update_fields=[
                'rsvp_status', 'food_preference', 'dietary_notes', 'rsvp_responded_at',
            ])
            return HttpResponse(render_to_string('events/rsvp_thankyou.html', {
                'guest': guest,
                'event': guest.event,
            }, request=request))

        return HttpResponse(render_to_string('events/rsvp_public.html', {
            'guest': guest,
            'event': guest.event,
            'form': form,
        }, request=request))
