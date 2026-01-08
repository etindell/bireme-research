"""
PDF export views.

Note: WeasyPrint requires GTK libraries on Windows.
For Windows development without GTK, PDF export will return HTML instead.
Install GTK on Windows: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows
"""
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.template.loader import render_to_string

from apps.companies.models import Company
from apps.notes.models import Note

# Try to import WeasyPrint, but make it optional
try:
    from django_weasyprint import WeasyTemplateResponseMixin
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    WeasyTemplateResponseMixin = object  # Dummy class


class BaseCompanyPDFView(LoginRequiredMixin, DetailView):
    """Base view for company PDF export."""
    model = Company
    template_name = 'export/company_pdf.html'

    def get_queryset(self):
        if hasattr(self.request, 'organization') and self.request.organization:
            return Company.objects.filter(organization=self.request.organization)
        return Company.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all notes for this company (primary + mentioned)
        notes = Note.objects.filter(
            organization=self.request.organization,
            is_deleted=False
        ).filter(
            models.Q(company=self.object) |
            models.Q(referenced_companies=self.object)
        ).select_related(
            'note_type', 'created_by'
        ).order_by('-created_at').distinct()

        context['notes'] = notes
        context['export_date'] = timezone.now()
        return context


if WEASYPRINT_AVAILABLE:
    class CompanyPDFView(WeasyTemplateResponseMixin, BaseCompanyPDFView):
        """Export company notes as PDF using WeasyPrint."""
        pdf_stylesheets = []

        def get_pdf_filename(self):
            return f'{self.object.slug}-notes-{timezone.now().strftime("%Y%m%d")}.pdf'
else:
    class CompanyPDFView(BaseCompanyPDFView):
        """
        Fallback: Export company notes as HTML when WeasyPrint is unavailable.
        The HTML is styled for printing.
        """
        def render_to_response(self, context, **response_kwargs):
            # Return printable HTML since WeasyPrint isn't available
            html = render_to_string(self.template_name, context, request=self.request)
            response = HttpResponse(html, content_type='text/html')
            response['Content-Disposition'] = f'inline; filename="{self.object.slug}-notes.html"'
            return response
