"""
Views for Note management.
"""
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from core.mixins import OrganizationViewMixin
from apps.companies.models import Company
from .models import Note, NoteType, NoteImage
from .forms import NoteForm, QuickNoteForm, ImportNotesForm


class NoteListView(OrganizationViewMixin, ListView):
    """List all notes with filtering."""
    model = Note
    template_name = 'notes/note_list.html'
    context_object_name = 'notes'
    paginate_by = 50

    def get_queryset(self):
        from django.db.models.functions import Coalesce

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

        # Order by display_date (written_at if set, otherwise created_at)
        qs = qs.annotate(
            effective_date=Coalesce('written_at', 'created_at')
        )
        return qs.order_by('-is_pinned', '-effective_date')

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


class NoteImageUploadView(LoginRequiredMixin, View):
    """
    Handle image uploads for notes.
    Accepts pasted/dropped images and returns the URL for embedding.
    """

    def post(self, request):
        if not hasattr(request, 'organization') or not request.organization:
            return JsonResponse({'error': 'No organization'}, status=400)

        if 'image' not in request.FILES:
            return JsonResponse({'error': 'No image provided'}, status=400)

        image_file = request.FILES['image']

        # Validate file type
        allowed_types = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
        if image_file.content_type not in allowed_types:
            return JsonResponse({'error': 'Invalid image type'}, status=400)

        # Limit file size (5MB)
        max_size = 5 * 1024 * 1024
        if image_file.size > max_size:
            return JsonResponse({'error': 'Image too large (max 5MB)'}, status=400)

        # Create the image record
        note_image = NoteImage.objects.create(
            organization=request.organization,
            image=image_file,
            uploaded_by=request.user,
            original_filename=image_file.name,
            file_size=image_file.size
        )

        return JsonResponse({
            'success': True,
            'url': note_image.url,
            'markdown': note_image.markdown,
            'id': note_image.pk
        })


class NoteImportView(OrganizationViewMixin, View):
    """
    Import notes from a Markdown file.
    Reuses parsing logic from the import_notes_md management command.
    """
    template_name = 'notes/import_form.html'

    def get(self, request):
        form = ImportNotesForm(organization=request.organization)
        # Pre-select company if provided in URL
        company_slug = request.GET.get('company')
        if company_slug:
            try:
                company = Company.objects.get(
                    organization=request.organization,
                    slug=company_slug
                )
                form.fields['company'].initial = company
            except Company.DoesNotExist:
                pass

        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = ImportNotesForm(request.POST, request.FILES, organization=request.organization)

        if form.is_valid():
            company = form.cleaned_data['company']
            uploaded_file = form.cleaned_data['file']
            note_type = form.cleaned_data.get('note_type')

            # Read file content
            content = uploaded_file.read().decode('utf-8')

            # Parse the file
            _, notes_data = self._parse_md_file(content)

            # Create notes
            created_count = 0
            for note_data in notes_data:
                title = note_data['title'][:500] if note_data['title'] else 'Imported note'
                if len(title) > 100:
                    title = title[:97] + '...'

                Note.objects.create(
                    organization=request.organization,
                    company=company,
                    title=title,
                    content=note_data['content'],
                    note_type=note_type,
                    written_at=note_data['written_at'],
                    created_by=request.user,
                )
                created_count += 1

            messages.success(request, f'Successfully imported {created_count} notes.')
            return redirect(company.get_absolute_url())

        return render(request, self.template_name, {'form': form})

    def _parse_date(self, date_str):
        """Parse various date formats from the MD file."""
        import re
        from datetime import datetime
        from django.utils import timezone

        date_str = date_str.replace('\ufeff', '').strip()

        formats = [
            "%a, %b %d, %Y",
            "%A, %b %d, %Y",
            "%a, %B %d, %Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%m/%d/%y",
            "%m/%d/%Y",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return timezone.make_aware(datetime.combine(dt.date(), datetime.min.time()))
            except ValueError:
                continue

        return None

    def _extract_date_from_text(self, text):
        """Try to extract a date from anywhere in the text."""
        import re

        text = text.replace('\ufeff', '').strip()

        patterns = [
            (r'([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})', '%a, %b %d, %Y'),
            (r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', '%b %d, %Y'),
            (r'(\d{1,2}/\d{1,2}/\d{2,4})', None),
        ]

        for pattern, date_fmt in patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)
                if parsed_date:
                    text_without_date = text[:match.start()] + text[match.end():]
                    text_without_date = re.sub(r'\s+', ' ', text_without_date).strip()
                    text_without_date = text_without_date.strip('-').strip()
                    return parsed_date, text_without_date

        return None, text

    def _parse_md_file(self, content):
        """Parse the markdown file and extract notes."""
        lines = content.split('\n')

        company_name = None
        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('-') and not stripped.startswith('#'):
                company_name = stripped
                start_idx = i + 1
                break

        notes = []
        current_note = None
        current_content_lines = []

        for i in range(start_idx, len(lines)):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                if current_note and current_content_lines:
                    current_content_lines.append('')
                continue

            indent = len(line) - len(line.lstrip())
            is_top_level_bullet = stripped.startswith('-') and indent == 0

            if is_top_level_bullet:
                if current_note:
                    current_note['content'] = '\n'.join(current_content_lines).strip()
                    notes.append(current_note)

                entry_text = stripped[1:].strip()
                parsed_date, title = self._extract_date_from_text(entry_text)

                current_note = {
                    'written_at': parsed_date,
                    'title': title if title else entry_text,
                    'content': '',
                }
                current_content_lines = []
                continue

            if current_note:
                current_content_lines.append(line.rstrip())

        if current_note:
            current_note['content'] = '\n'.join(current_content_lines).strip()
            notes.append(current_note)

        # Fill in missing dates from next note
        last_known_date = None
        for note in reversed(notes):
            if note['written_at']:
                last_known_date = note['written_at']
            elif last_known_date:
                note['written_at'] = last_known_date

        return company_name, notes


# Need to import render for the import view
from django.shortcuts import render, redirect
