from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import HttpResponse
from django.template.loader import render_to_string

from core.mixins import OrganizationViewMixin
from .models import Prospect, ProspectNote
from .forms import ProspectForm
from .services.hubspot import sync_prospect_to_hubspot, sync_note_to_hubspot

class ProspectListView(OrganizationViewMixin, ListView):
    model = Prospect
    template_name = 'prospects/prospect_list.html'
    context_object_name = 'prospects'

    def get_queryset(self):
        return Prospect.objects.filter(organization=self.request.organization)

class ProspectDetailView(OrganizationViewMixin, DetailView):
    model = Prospect
    template_name = 'prospects/prospect_detail.html'
    context_object_name = 'prospect'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['notes'] = self.object.prospect_notes.all().select_related('user')
        return ctx

class ProspectCreateView(OrganizationViewMixin, CreateView):
    model = Prospect
    form_class = ProspectForm
    template_name = 'prospects/prospect_form.html'
    success_url = reverse_lazy('prospects:list')

    def form_valid(self, form):
        form.instance.organization = self.request.organization
        res = super().form_valid(form)
        # Sync to HubSpot
        hs_id = sync_prospect_to_hubspot(self.object)
        if hs_id:
            messages.success(self.request, f"Prospect {self.object} created and synced to HubSpot.")
        else:
            messages.warning(self.request, f"Prospect {self.object} created, but HubSpot sync failed. You can retry from the detail page.")
        return res

class ProspectUpdateView(OrganizationViewMixin, UpdateView):
    model = Prospect
    form_class = ProspectForm
    template_name = 'prospects/prospect_form.html'

    def get_success_url(self):
        return reverse('prospects:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        res = super().form_valid(form)
        # Sync to HubSpot
        hs_id = sync_prospect_to_hubspot(self.object)
        if hs_id:
            messages.success(self.request, f"Prospect {self.object} updated and synced to HubSpot.")
        else:
            messages.warning(self.request, f"Prospect {self.object} updated, but HubSpot sync failed. You can retry from the detail page.")
        return res

class AddProspectNoteView(OrganizationViewMixin, View):
    """HTMX view to add a note to a prospect."""
    def post(self, request, pk):
        prospect = get_object_or_404(Prospect.objects.filter(organization=request.organization), pk=pk)
        content = request.POST.get('content')
        
        if content:
            note = ProspectNote.objects.create(
                organization=request.organization,
                prospect=prospect,
                user=request.user,
                content=content
            )
            # Sync to HubSpot
            if prospect.hubspot_id:
                note_id = sync_note_to_hubspot(note)
                if not note_id:
                    messages.warning(request, "Note saved locally but HubSpot sync failed.")
            else:
                messages.info(request, "Note saved. It will sync to HubSpot when the prospect is synced.")

            if request.htmx:
                html = render_to_string('prospects/partials/note_item.html', {'note': note})
                return HttpResponse(html)
        
        return redirect('prospects:detail', pk=pk)

class SyncProspectView(OrganizationViewMixin, View):
    """Trigger manual sync to HubSpot."""
    def post(self, request, pk):
        prospect = get_object_or_404(Prospect.objects.filter(organization=request.organization), pk=pk)
        sync_prospect_to_hubspot(prospect)
        
        # Also sync notes that haven't been synced?
        for note in prospect.prospect_notes.filter(hubspot_note_id=''):
            sync_note_to_hubspot(note)
            
        messages.success(request, f"Sync for {prospect} completed.")
        return redirect('prospects:detail', pk=pk)
