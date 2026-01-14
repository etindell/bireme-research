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
from .models import Note, NoteType, NoteImage, NoteCashFlow
from .forms import NoteForm, QuickNoteForm, ImportNotesForm, NoteCashFlowForm


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
    preselected_company = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # Pre-fetch company from URL parameter for use throughout view
        company_slug = request.GET.get('company')
        if company_slug and getattr(request, 'organization', None):
            try:
                self.preselected_company = Company.objects.get(
                    organization=request.organization,
                    slug=company_slug
                )
            except Company.DoesNotExist:
                pass

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organization'] = self.request.organization
        return kwargs

    def get_initial(self):
        from apps.todos.models import Todo

        initial = super().get_initial()

        # Use preselected company from URL
        if self.preselected_company:
            initial['company'] = self.preselected_company

        # Pre-select todo if provided in URL (for completing from todo page)
        todo_id = self.request.GET.get('todo')
        if todo_id:
            try:
                todo = Todo.objects.get(
                    pk=todo_id,
                    organization=self.request.organization,
                    is_completed=False,
                    is_deleted=False
                )
                initial['complete_todo'] = todo
                # Also pre-select the company from the todo if not already set
                if not self.preselected_company and todo.company:
                    initial['company'] = todo.company
                    self.preselected_company = todo.company
            except (Todo.DoesNotExist, ValueError):
                pass

        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'cash_flow_form' not in context:
            context['cash_flow_form'] = NoteCashFlowForm()

        # Pass preselected company to context for profitability_metric label
        if self.preselected_company:
            context['company'] = self.preselected_company

        return context

    def form_valid(self, form):
        # Pre-validate cash flow form BEFORE saving the note
        # This ensures users see validation errors instead of silent failure
        if self.request.POST.get('include_cash_flows'):
            cash_flow_form = NoteCashFlowForm(self.request.POST)
            if not cash_flow_form.is_valid():
                # Re-render form with cash flow errors - don't save the note
                context = self.get_context_data(form=form, cash_flow_form=cash_flow_form)
                return self.render_to_response(context)

        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        # Handle cash flow form (already validated above if checkbox was checked)
        cash_flow_form = NoteCashFlowForm(self.request.POST)
        if cash_flow_form.is_valid() and cash_flow_form.cleaned_data.get('include_cash_flows'):
            cash_flow = NoteCashFlow(
                note=self.object,
                current_price=cash_flow_form.cleaned_data['current_price'],
                fcf_year_1=cash_flow_form.cleaned_data['fcf_year_1'],
                fcf_year_2=cash_flow_form.cleaned_data['fcf_year_2'],
                fcf_year_3=cash_flow_form.cleaned_data['fcf_year_3'],
                fcf_year_4=cash_flow_form.cleaned_data['fcf_year_4'],
                fcf_year_5=cash_flow_form.cleaned_data['fcf_year_5'],
                terminal_value=cash_flow_form.cleaned_data['terminal_value'],
                # Revenue projections (optional)
                revenue_year_1=cash_flow_form.cleaned_data.get('revenue_year_1'),
                revenue_year_2=cash_flow_form.cleaned_data.get('revenue_year_2'),
                revenue_year_3=cash_flow_form.cleaned_data.get('revenue_year_3'),
                revenue_year_4=cash_flow_form.cleaned_data.get('revenue_year_4'),
                revenue_year_5=cash_flow_form.cleaned_data.get('revenue_year_5'),
                # EBIT/EBITDA projections (optional)
                ebit_ebitda_year_1=cash_flow_form.cleaned_data.get('ebit_ebitda_year_1'),
                ebit_ebitda_year_2=cash_flow_form.cleaned_data.get('ebit_ebitda_year_2'),
                ebit_ebitda_year_3=cash_flow_form.cleaned_data.get('ebit_ebitda_year_3'),
                ebit_ebitda_year_4=cash_flow_form.cleaned_data.get('ebit_ebitda_year_4'),
                ebit_ebitda_year_5=cash_flow_form.cleaned_data.get('ebit_ebitda_year_5'),
            )
            cash_flow.calculated_irr = cash_flow.calculate_irr()
            cash_flow.save()

            # Also update or create the company's active valuation
            self._update_company_valuation(cash_flow_form.cleaned_data)

        # Handle todo completion
        complete_todo = form.cleaned_data.get('complete_todo')
        if complete_todo:
            complete_todo.mark_complete(user=self.request.user, note=self.object)
            messages.success(self.request, f'Note created and todo "{complete_todo.title[:50]}" marked complete.')
        else:
            messages.success(self.request, 'Note created.')

        return response

    def _update_company_valuation(self, cleaned_data):
        """Update or create the company's active valuation with the cash flow data."""
        from apps.companies.models import CompanyValuation
        from django.utils import timezone

        company = self.object.company
        today = timezone.now().date()

        # Get existing active valuation or create new one
        valuation = company.get_active_valuation()

        if valuation:
            # Update existing valuation
            valuation.fcf_year_1 = cleaned_data['fcf_year_1']
            valuation.fcf_year_2 = cleaned_data['fcf_year_2']
            valuation.fcf_year_3 = cleaned_data['fcf_year_3']
            valuation.fcf_year_4 = cleaned_data['fcf_year_4']
            valuation.fcf_year_5 = cleaned_data['fcf_year_5']
            valuation.terminal_value = cleaned_data['terminal_value']
            valuation.price_override = cleaned_data['current_price']
            valuation.as_of_date = today
            valuation.calculate_irr()
            valuation.save(history_user=self.request.user)
        else:
            # Create new valuation
            valuation = CompanyValuation.objects.create(
                company=company,
                fcf_year_1=cleaned_data['fcf_year_1'],
                fcf_year_2=cleaned_data['fcf_year_2'],
                fcf_year_3=cleaned_data['fcf_year_3'],
                fcf_year_4=cleaned_data['fcf_year_4'],
                fcf_year_5=cleaned_data['fcf_year_5'],
                terminal_value=cleaned_data['terminal_value'],
                price_override=cleaned_data['current_price'],
                as_of_date=today,
                is_active=True,
            )
            valuation.calculate_irr()
            valuation.save(history_user=self.request.user)

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'cash_flow_form' not in context:
            # Pre-populate form if note has existing cash flows
            initial = {}
            try:
                cash_flow = self.object.cash_flow
                initial = {
                    'include_cash_flows': True,
                    'current_price': cash_flow.current_price,
                    'fcf_year_1': cash_flow.fcf_year_1,
                    'fcf_year_2': cash_flow.fcf_year_2,
                    'fcf_year_3': cash_flow.fcf_year_3,
                    'fcf_year_4': cash_flow.fcf_year_4,
                    'fcf_year_5': cash_flow.fcf_year_5,
                    'terminal_value': cash_flow.terminal_value,
                    # Revenue projections
                    'revenue_year_1': cash_flow.revenue_year_1,
                    'revenue_year_2': cash_flow.revenue_year_2,
                    'revenue_year_3': cash_flow.revenue_year_3,
                    'revenue_year_4': cash_flow.revenue_year_4,
                    'revenue_year_5': cash_flow.revenue_year_5,
                    # EBIT/EBITDA projections
                    'ebit_ebitda_year_1': cash_flow.ebit_ebitda_year_1,
                    'ebit_ebitda_year_2': cash_flow.ebit_ebitda_year_2,
                    'ebit_ebitda_year_3': cash_flow.ebit_ebitda_year_3,
                    'ebit_ebitda_year_4': cash_flow.ebit_ebitda_year_4,
                    'ebit_ebitda_year_5': cash_flow.ebit_ebitda_year_5,
                }
            except NoteCashFlow.DoesNotExist:
                pass
            context['cash_flow_form'] = NoteCashFlowForm(initial=initial)

        # Pass company to context for profitability_metric label in template
        context['company'] = self.object.company

        return context

    def form_valid(self, form):
        # Pre-validate cash flow form BEFORE saving the note
        # This ensures users see validation errors instead of silent failure
        if self.request.POST.get('include_cash_flows'):
            cash_flow_form = NoteCashFlowForm(self.request.POST)
            if not cash_flow_form.is_valid():
                # Re-render form with cash flow errors - don't save the note
                context = self.get_context_data(form=form, cash_flow_form=cash_flow_form)
                return self.render_to_response(context)

        form.instance.updated_by = self.request.user
        response = super().form_valid(form)

        # Handle cash flow form (already validated above if checkbox was checked)
        cash_flow_form = NoteCashFlowForm(self.request.POST)
        if cash_flow_form.is_valid():
            include = cash_flow_form.cleaned_data.get('include_cash_flows')
            try:
                existing_cash_flow = self.object.cash_flow
                if include:
                    # Update existing
                    existing_cash_flow.current_price = cash_flow_form.cleaned_data['current_price']
                    existing_cash_flow.fcf_year_1 = cash_flow_form.cleaned_data['fcf_year_1']
                    existing_cash_flow.fcf_year_2 = cash_flow_form.cleaned_data['fcf_year_2']
                    existing_cash_flow.fcf_year_3 = cash_flow_form.cleaned_data['fcf_year_3']
                    existing_cash_flow.fcf_year_4 = cash_flow_form.cleaned_data['fcf_year_4']
                    existing_cash_flow.fcf_year_5 = cash_flow_form.cleaned_data['fcf_year_5']
                    existing_cash_flow.terminal_value = cash_flow_form.cleaned_data['terminal_value']
                    # Revenue projections (optional)
                    existing_cash_flow.revenue_year_1 = cash_flow_form.cleaned_data.get('revenue_year_1')
                    existing_cash_flow.revenue_year_2 = cash_flow_form.cleaned_data.get('revenue_year_2')
                    existing_cash_flow.revenue_year_3 = cash_flow_form.cleaned_data.get('revenue_year_3')
                    existing_cash_flow.revenue_year_4 = cash_flow_form.cleaned_data.get('revenue_year_4')
                    existing_cash_flow.revenue_year_5 = cash_flow_form.cleaned_data.get('revenue_year_5')
                    # EBIT/EBITDA projections (optional)
                    existing_cash_flow.ebit_ebitda_year_1 = cash_flow_form.cleaned_data.get('ebit_ebitda_year_1')
                    existing_cash_flow.ebit_ebitda_year_2 = cash_flow_form.cleaned_data.get('ebit_ebitda_year_2')
                    existing_cash_flow.ebit_ebitda_year_3 = cash_flow_form.cleaned_data.get('ebit_ebitda_year_3')
                    existing_cash_flow.ebit_ebitda_year_4 = cash_flow_form.cleaned_data.get('ebit_ebitda_year_4')
                    existing_cash_flow.ebit_ebitda_year_5 = cash_flow_form.cleaned_data.get('ebit_ebitda_year_5')
                    existing_cash_flow.calculated_irr = existing_cash_flow.calculate_irr()
                    existing_cash_flow.save()
                    # Also update company valuation
                    self._update_company_valuation(cash_flow_form.cleaned_data)
                else:
                    # Remove cash flows if unchecked
                    existing_cash_flow.delete()
            except NoteCashFlow.DoesNotExist:
                if include:
                    # Create new
                    cash_flow = NoteCashFlow(
                        note=self.object,
                        current_price=cash_flow_form.cleaned_data['current_price'],
                        fcf_year_1=cash_flow_form.cleaned_data['fcf_year_1'],
                        fcf_year_2=cash_flow_form.cleaned_data['fcf_year_2'],
                        fcf_year_3=cash_flow_form.cleaned_data['fcf_year_3'],
                        fcf_year_4=cash_flow_form.cleaned_data['fcf_year_4'],
                        fcf_year_5=cash_flow_form.cleaned_data['fcf_year_5'],
                        terminal_value=cash_flow_form.cleaned_data['terminal_value'],
                        # Revenue projections (optional)
                        revenue_year_1=cash_flow_form.cleaned_data.get('revenue_year_1'),
                        revenue_year_2=cash_flow_form.cleaned_data.get('revenue_year_2'),
                        revenue_year_3=cash_flow_form.cleaned_data.get('revenue_year_3'),
                        revenue_year_4=cash_flow_form.cleaned_data.get('revenue_year_4'),
                        revenue_year_5=cash_flow_form.cleaned_data.get('revenue_year_5'),
                        # EBIT/EBITDA projections (optional)
                        ebit_ebitda_year_1=cash_flow_form.cleaned_data.get('ebit_ebitda_year_1'),
                        ebit_ebitda_year_2=cash_flow_form.cleaned_data.get('ebit_ebitda_year_2'),
                        ebit_ebitda_year_3=cash_flow_form.cleaned_data.get('ebit_ebitda_year_3'),
                        ebit_ebitda_year_4=cash_flow_form.cleaned_data.get('ebit_ebitda_year_4'),
                        ebit_ebitda_year_5=cash_flow_form.cleaned_data.get('ebit_ebitda_year_5'),
                    )
                    cash_flow.calculated_irr = cash_flow.calculate_irr()
                    cash_flow.save()
                    # Also update company valuation
                    self._update_company_valuation(cash_flow_form.cleaned_data)

        messages.success(self.request, 'Note updated.')
        return response

    def _update_company_valuation(self, cleaned_data):
        """Update or create the company's active valuation with the cash flow data."""
        from apps.companies.models import CompanyValuation
        from django.utils import timezone

        company = self.object.company
        today = timezone.now().date()

        # Get existing active valuation or create new one
        valuation = company.get_active_valuation()

        if valuation:
            # Update existing valuation
            valuation.fcf_year_1 = cleaned_data['fcf_year_1']
            valuation.fcf_year_2 = cleaned_data['fcf_year_2']
            valuation.fcf_year_3 = cleaned_data['fcf_year_3']
            valuation.fcf_year_4 = cleaned_data['fcf_year_4']
            valuation.fcf_year_5 = cleaned_data['fcf_year_5']
            valuation.terminal_value = cleaned_data['terminal_value']
            valuation.price_override = cleaned_data['current_price']
            valuation.as_of_date = today
            valuation.calculate_irr()
            valuation.save(history_user=self.request.user)
        else:
            # Create new valuation
            valuation = CompanyValuation.objects.create(
                company=company,
                fcf_year_1=cleaned_data['fcf_year_1'],
                fcf_year_2=cleaned_data['fcf_year_2'],
                fcf_year_3=cleaned_data['fcf_year_3'],
                fcf_year_4=cleaned_data['fcf_year_4'],
                fcf_year_5=cleaned_data['fcf_year_5'],
                terminal_value=cleaned_data['terminal_value'],
                price_override=cleaned_data['current_price'],
                as_of_date=today,
                is_active=True,
            )
            valuation.calculate_irr()
            valuation.save(history_user=self.request.user)


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
            company = form.cleaned_data.get('company')  # May be None for batch
            uploaded_file = form.cleaned_data['file']
            note_type = form.cleaned_data.get('note_type')

            # Read file content
            content = uploaded_file.read().decode('utf-8')

            # Parse the file
            _, notes_data = self._parse_md_file(content, default_company=company)

            # Build company lookup cache
            company_cache = {}

            # Create notes
            created_count = 0
            skipped_companies = set()

            for note_data in notes_data:
                # Determine which company to use
                note_company = company  # Default from form

                if note_data.get('company_name'):
                    company_name = note_data['company_name']

                    # Try to find company by name (case-insensitive)
                    if company_name not in company_cache:
                        found_company = Company.objects.filter(
                            organization=request.organization,
                            name__iexact=company_name,
                            is_deleted=False
                        ).first()
                        company_cache[company_name] = found_company

                    note_company = company_cache[company_name]

                    if not note_company:
                        skipped_companies.add(company_name)
                        continue

                if not note_company:
                    continue

                title = note_data['title'][:500] if note_data['title'] else 'Imported note'
                if len(title) > 100:
                    title = title[:97] + '...'

                Note.objects.create(
                    organization=request.organization,
                    company=note_company,
                    title=title,
                    content=note_data['content'],
                    note_type=note_type,
                    written_at=note_data['written_at'],
                    is_imported=True,
                    created_by=request.user,
                )
                created_count += 1

            # Build success message
            msg = f'Successfully imported {created_count} notes.'
            if skipped_companies:
                msg += f' Skipped notes for unknown companies: {", ".join(sorted(skipped_companies))}'

            messages.success(request, msg)

            # Redirect to company page if single company, otherwise notes list
            if company:
                return redirect(company.get_absolute_url())
            return redirect('notes:list')

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

    def _parse_md_file(self, content, default_company=None):
        """
        Parse the markdown file and extract notes.

        If default_company is provided (from form), all notes go to that company
        and company names in the file are ignored.

        If no default_company, uses batch format where first-level bullets are
        company names that must match existing companies.
        """
        lines = content.split('\n')

        # Detect format: if first non-empty line is a bullet, it's hierarchical format
        is_hierarchical = False
        for line in lines:
            stripped = line.strip()
            if stripped:
                if stripped.startswith('-'):
                    is_hierarchical = True
                break

        if is_hierarchical:
            return self._parse_hierarchical_format(lines, default_company)
        else:
            return self._parse_flat_format(lines, default_company)

    def _parse_flat_format(self, lines, default_company=None):
        """
        Parse flat format where notes are top-level bullets.
        Company name on first line is ignored if default_company provided.
        """
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
                    'company_name': None,  # Will use default_company
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

    def _parse_hierarchical_format(self, lines, default_company=None):
        """
        Parse hierarchical bullet format.

        If default_company is provided:
          - First level bullet = Note title (with date)
          - Second level bullet = Note content
          - Company names in file are ignored

        If no default_company (batch mode):
          - First level bullet = Company name
          - Second level bullet = Note title (with date)
          - Third level bullet = Note content
        """
        notes = []
        current_company_name = None
        current_note = None
        current_content_lines = []

        def get_indent_level(line):
            """Get the indent level (number of leading spaces/tabs)."""
            stripped = line.lstrip()
            if not stripped.startswith('-'):
                return -1
            indent = len(line) - len(line.lstrip())
            # Normalize: 0 = level 1, 2-4 = level 2, 4+ = level 3
            if indent == 0:
                return 1
            elif indent <= 4:
                return 2
            else:
                return 3

        for line in lines:
            stripped = line.strip()

            if not stripped:
                if current_note and current_content_lines:
                    current_content_lines.append('')
                continue

            if not stripped.startswith('-'):
                # Non-bullet line - add to content if we have a note
                if current_note:
                    current_content_lines.append(stripped)
                continue

            level = get_indent_level(line)
            bullet_text = stripped[1:].strip()

            if default_company:
                # Single company mode: level 1 = company (ignored), level 2 = note title, level 3 = content
                if level == 1:
                    # Company name - ignore it, save previous note if exists
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)
                        current_note = None
                        current_content_lines = []
                    # Skip company name - we use default_company

                elif level == 2:
                    # Note title with date
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)

                    parsed_date, title = self._extract_date_from_text(bullet_text)

                    current_note = {
                        'company_name': None,  # Will use default_company
                        'written_at': parsed_date,
                        'title': title if title else bullet_text,
                        'content': '',
                    }
                    current_content_lines = []

                elif level == 3 and current_note:
                    # Content at section header level - bold/underline (unless #mythoughts)
                    if '#mythoughts' not in bullet_text.lower():
                        bullet_text = f"**__{bullet_text}__**"
                    current_content_lines.append(bullet_text)

                elif level > 3 and current_note:
                    # Deeper content - no formatting
                    current_content_lines.append(bullet_text)

            else:
                # Batch mode: level 1 = company, level 2 = note title, level 3 = content
                if level == 1:
                    # First level = Company name
                    # Save previous note if exists
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)
                        current_note = None
                        current_content_lines = []

                    current_company_name = bullet_text

                elif level == 2:
                    # Second level = Note title with date
                    # Save previous note if exists
                    if current_note:
                        current_note['content'] = '\n'.join(current_content_lines).strip()
                        notes.append(current_note)

                    parsed_date, title = self._extract_date_from_text(bullet_text)

                    current_note = {
                        'company_name': current_company_name,
                        'written_at': parsed_date,
                        'title': title if title else bullet_text,
                        'content': '',
                    }
                    current_content_lines = []

                elif level == 3 and current_note:
                    # Content at section header level - bold/underline (unless #mythoughts)
                    if '#mythoughts' not in bullet_text.lower():
                        bullet_text = f"**__{bullet_text}__**"
                    current_content_lines.append(bullet_text)

                elif level > 3 and current_note:
                    # Deeper content - no formatting
                    current_content_lines.append(bullet_text)

        # Save last note
        if current_note:
            current_note['content'] = '\n'.join(current_content_lines).strip()
            notes.append(current_note)

        # Fill in missing dates from next note (within same company for batch)
        last_known_date = None
        last_company = None
        for note in reversed(notes):
            if not default_company and note['company_name'] != last_company:
                last_known_date = None
                last_company = note['company_name']

            if note['written_at']:
                last_known_date = note['written_at']
            elif last_known_date:
                note['written_at'] = last_known_date

        return None, notes


# Need to import render for the import view
from django.shortcuts import render, redirect


class NoteBulkDeleteView(OrganizationViewMixin, View):
    """Handle bulk deletion of notes."""

    def post(self, request):
        note_ids = request.POST.getlist('note_ids')

        if not note_ids:
            messages.warning(request, 'No notes selected.')
            return redirect('notes:list')

        # Filter to only notes in the user's organization
        notes = Note.objects.filter(
            organization=request.organization,
            pk__in=note_ids
        )

        count = notes.count()

        # Soft delete each note
        for note in notes:
            note.delete(user=request.user)

        messages.success(request, f'Deleted {count} note{"s" if count != 1 else ""}.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return redirect('notes:list')
