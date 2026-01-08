"""
Views for Company management.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View

from core.mixins import OrganizationViewMixin
from .models import Company
from .forms import CompanyForm, CompanyTickerFormSet, CompanyStatusForm


class CompanyListView(OrganizationViewMixin, ListView):
    """List all companies with filtering."""
    model = Company
    template_name = 'companies/company_list.html'
    context_object_name = 'companies'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('tickers')

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        # Filter by sector
        sector = self.request.GET.get('sector')
        if sector:
            qs = qs.filter(sector=sector)

        # Search
        q = self.request.GET.get('q')
        if q:
            qs = qs.search(q)

        # Ordering
        order = self.request.GET.get('order', 'name')
        if order == '-updated_at':
            qs = qs.order_by('-updated_at')
        else:
            qs = qs.order_by('name')

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = Company.Status.choices
        context['sectors'] = Company.Sector.choices
        context['current_status'] = self.request.GET.get('status', '')
        context['current_sector'] = self.request.GET.get('sector', '')
        context['current_order'] = self.request.GET.get('order', 'name')
        context['search_query'] = self.request.GET.get('q', '')
        return context

    def get_template_names(self):
        if self.request.htmx:
            return ['companies/partials/company_list_items.html']
        return [self.template_name]


class CompanyDetailView(OrganizationViewMixin, DetailView):
    """Company detail page with notes."""
    model = Company
    template_name = 'companies/company_detail.html'
    context_object_name = 'company'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('tickers')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get notes for this company (primary + mentioned)
        from apps.notes.models import Note
        context['notes'] = Note.objects.filter(
            organization=self.request.organization,
            is_deleted=False
        ).filter(
            models.Q(company=self.object) |
            models.Q(referenced_companies=self.object)
        ).select_related(
            'note_type', 'created_by', 'company'
        ).order_by('-created_at').distinct()[:50]

        context['statuses'] = Company.Status.choices
        return context


class CompanyCreateView(OrganizationViewMixin, CreateView):
    """Create a new company."""
    model = Company
    form_class = CompanyForm
    template_name = 'companies/company_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['ticker_formset'] = CompanyTickerFormSet(self.request.POST)
        else:
            context['ticker_formset'] = CompanyTickerFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ticker_formset = context['ticker_formset']

        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user

        if ticker_formset.is_valid():
            response = super().form_valid(form)
            ticker_formset.instance = self.object
            ticker_formset.save()
            messages.success(self.request, f'Company "{self.object.name}" created.')
            return response
        else:
            return self.form_invalid(form)


class CompanyUpdateView(OrganizationViewMixin, UpdateView):
    """Update a company."""
    model = Company
    form_class = CompanyForm
    template_name = 'companies/company_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['ticker_formset'] = CompanyTickerFormSet(self.request.POST, instance=self.object)
        else:
            context['ticker_formset'] = CompanyTickerFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ticker_formset = context['ticker_formset']

        form.instance.updated_by = self.request.user

        if ticker_formset.is_valid():
            response = super().form_valid(form)
            ticker_formset.save()
            messages.success(self.request, 'Company updated.')
            return response
        else:
            return self.form_invalid(form)


class CompanyDeleteView(OrganizationViewMixin, DeleteView):
    """Soft delete a company."""
    model = Company
    success_url = reverse_lazy('companies:list')

    def form_valid(self, form):
        self.object.delete(user=self.request.user)
        messages.success(self.request, f'Company "{self.object.name}" deleted.')
        return HttpResponse(status=204, headers={'HX-Redirect': self.success_url})


class CompanyStatusUpdateView(OrganizationViewMixin, View):
    """HTMX view to update company status."""

    def post(self, request, slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=slug
        )
        form = CompanyStatusForm(request.POST, instance=company)

        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()

            # Return updated status badge
            html = render_to_string(
                'companies/partials/status_badge.html',
                {'status': company.status, 'company': company},
                request=request
            )
            return HttpResponse(html)

        return HttpResponse(status=400)


# Import models for Q lookup
from django.db import models
