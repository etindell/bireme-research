"""
Views for Note management.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View

from core.mixins import OrganizationViewMixin
from apps.companies.models import Company
from .models import Note, NoteType
from .forms import NoteForm, QuickNoteForm


class NoteListView(OrganizationViewMixin, ListView):
    """List all notes with filtering."""
    model = Note
    template_name = 'notes/note_list.html'
    context_object_name = 'notes'
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().root_notes().select_related(
            'company', 'note_type', 'created_by'
        ).prefetch_related('children')

        # Filter by company
        company_slug = self.request.GET.get('company')
        if company_slug:
            company = get_object_or_404(
                Company,
                organization=self.request.organization,
                slug=company_slug
            )
            qs = qs.for_company(company)

        # Filter by type
        note_type = self.request.GET.get('type')
        if note_type:
            qs = qs.filter(note_type__slug=note_type)

        # Search
        q = self.request.GET.get('q')
        if q:
            qs = qs.search(q)

        return qs.order_by('-is_pinned', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['note_types'] = NoteType.objects.filter(
            organization=self.request.organization
        )
        context['companies'] = Company.objects.filter(
            organization=self.request.organization
        )[:20]
        context['current_type'] = self.request.GET.get('type', '')
        context['current_company'] = self.request.GET.get('company', '')
        context['search_query'] = self.request.GET.get('q', '')
        return context


class NoteDetailView(OrganizationViewMixin, DetailView):
    """Note detail with children."""
    model = Note
    template_name = 'notes/note_detail.html'
    context_object_name = 'note'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'company', 'note_type', 'created_by', 'parent'
        ).prefetch_related('referenced_companies', 'children')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ancestors'] = self.object.get_ancestors()
        context['children'] = self.object.get_children()
        return context


class NoteCreateView(OrganizationViewMixin, CreateView):
    """Create a new note."""
    model = Note
    form_class = NoteForm
    template_name = 'notes/note_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organization'] = self.request.organization
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Pre-select company if provided in URL
        company_slug = self.request.GET.get('company')
        if company_slug:
            try:
                company = Company.objects.get(
                    organization=self.request.organization,
                    slug=company_slug
                )
                initial['company'] = company
            except Company.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Note created.')
        return response

    def get_success_url(self):
        # Return to company page if we came from there
        if self.request.GET.get('company'):
            return self.object.company.get_absolute_url()
        return self.object.get_absolute_url()


class NoteUpdateView(OrganizationViewMixin, UpdateView):
    """Update a note."""
    model = Note
    form_class = NoteForm
    template_name = 'notes/note_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organization'] = self.request.organization
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Note updated.')
        return response


class NoteDeleteView(OrganizationViewMixin, DeleteView):
    """Soft delete a note."""
    model = Note

    def get_success_url(self):
        return self.object.company.get_absolute_url()

    def form_valid(self, form):
        self.object.delete(user=self.request.user)
        messages.success(self.request, 'Note deleted.')
        if self.request.htmx:
            return HttpResponse(status=204)
        return HttpResponse(status=302, headers={'Location': self.get_success_url()})


class NoteToggleCollapseView(OrganizationViewMixin, View):
    """HTMX view to toggle note collapse state."""

    def post(self, request, pk):
        note = get_object_or_404(
            Note.objects.filter(organization=request.organization),
            pk=pk
        )
        note.is_collapsed = not note.is_collapsed
        note.save(update_fields=['is_collapsed'])

        # Return updated note card
        html = render_to_string(
            'notes/partials/note_card.html',
            {'note': note, 'show_company': True},
            request=request
        )
        return HttpResponse(html)


class NoteTogglePinView(OrganizationViewMixin, View):
    """HTMX view to toggle note pin state."""

    def post(self, request, pk):
        note = get_object_or_404(
            Note.objects.filter(organization=request.organization),
            pk=pk
        )
        note.is_pinned = not note.is_pinned
        note.save(update_fields=['is_pinned'])

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
