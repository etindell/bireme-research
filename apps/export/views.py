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

from .services.pdf_service import generate_note_pdf, generate_company_pdf


class NotePDFView(LoginRequiredMixin, DetailView):
    """Export individual note as a professional PDF."""
    model = Note

    def get_queryset(self):
        if hasattr(self.request, 'organization') and self.request.organization:
            return Note.objects.filter(
                organization=self.request.organization,
                is_deleted=False,
            ).select_related('company', 'note_type', 'created_by')
        return Note.objects.none()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        pdf_content = generate_note_pdf(self.object, request.user)
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        slug = self.object.company.slug if self.object.company else 'note'
        filename = f'{slug}-{self.object.pk}-{timezone.now().strftime("%Y%m%d")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class CompanyPDFView(LoginRequiredMixin, DetailView):
    """Export all company notes as a professional PDF compilation."""
    model = Company

    def get_queryset(self):
        if hasattr(self.request, 'organization') and self.request.organization:
            return Company.objects.filter(organization=self.request.organization)
        return Company.objects.none()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        
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

        pdf_content = generate_company_pdf(self.object, notes, request.user)
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        filename = f'{self.object.slug}-notes-{timezone.now().strftime("%Y%m%d")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
