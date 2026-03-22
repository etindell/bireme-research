import calendar as cal
from datetime import date, timedelta

from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView,
)

from core.mixins import OrganizationViewMixin
from .models import (
    ComplianceSettings, ComplianceObligation, ComplianceTask,
    ComplianceEvidence, ComplianceAuditLog, ComplianceDocument, SECNewsItem,
    Fund, FundPrincipal, InvestorJurisdiction,
    SurveyTemplate, SurveyVersion, SurveyQuestion, SurveyAssignment,
    SurveyResponse, SurveyAnswer, SurveyEvidenceUpload, SurveyException,
)
# Backwards compat alias used in existing views
ComplianceTaskTemplate = ComplianceObligation
from .forms import (
    ComplianceSettingsForm, ComplianceObligationForm, ComplianceTaskForm,
    EvidenceUploadForm, ComplianceDocumentForm, SurveyCompleteForm,
)
ComplianceTaskTemplateForm = ComplianceObligationForm
from .services.audit import log_action
from .services.task_generation import generate_tasks
from .services.surveys import assign_periodic_surveys, process_survey_submission


# ============ Dashboard ============

class ComplianceDashboardView(OrganizationViewMixin, TemplateView):
    template_name = 'compliance/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.organization
        now = timezone.now().date()
        year = int(self.request.GET.get('year', now.year))

        tasks = ComplianceTask.objects.filter(organization=org, year=year)
        total = tasks.count()
        completed = tasks.filter(status=ComplianceTask.Status.COMPLETED).count()
        in_progress = tasks.filter(status=ComplianceTask.Status.IN_PROGRESS).count()
        overdue = tasks.filter(
            due_date__lt=now
        ).exclude(
            status__in=[ComplianceTask.Status.COMPLETED, ComplianceTask.Status.NOT_APPLICABLE]
        ).count()

        ctx.update({
            'year': year,
            'total': total,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'completion_rate': round(completed / total * 100, 1) if total else 0,
            'upcoming': tasks.filter(
                due_date__gte=now, due_date__lte=now + timedelta(days=14)
            ).exclude(
                status__in=[ComplianceTask.Status.COMPLETED, ComplianceTask.Status.NOT_APPLICABLE]
            ).order_by('due_date')[:10],
            'overdue_tasks': tasks.filter(
                due_date__lt=now
            ).exclude(
                status__in=[ComplianceTask.Status.COMPLETED, ComplianceTask.Status.NOT_APPLICABLE]
            ).order_by('due_date')[:10],
        })
        return ctx


# ============ Settings ============

class ComplianceSettingsView(OrganizationViewMixin, View):
    def get(self, request):
        org = request.organization
        settings_obj, _ = ComplianceSettings.objects.get_or_create(
            organization=org,
            defaults={'created_by': request.user}
        )
        form = ComplianceSettingsForm(instance=settings_obj, organization=org)
        return self._render(request, form, settings_obj)

    def post(self, request):
        org = request.organization
        settings_obj, _ = ComplianceSettings.objects.get_or_create(
            organization=org,
            defaults={'created_by': request.user}
        )
        form = ComplianceSettingsForm(request.POST, instance=settings_obj, organization=org)
        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()
            messages.success(request, 'Compliance settings saved.')
            return redirect('compliance:settings')
        return self._render(request, form, settings_obj)

    def _render(self, request, form, settings_obj):
        from django.template.response import TemplateResponse
        return TemplateResponse(request, 'compliance/settings.html', {
            'form': form,
            'settings_obj': settings_obj,
        })


# ============ Task Templates (Phase 2) ============

class TemplateListView(OrganizationViewMixin, ListView):
    model = ComplianceTaskTemplate
    template_name = 'compliance/template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        qs = super().get_queryset()
        freq = self.request.GET.get('frequency')
        if freq:
            qs = qs.filter(frequency=freq)
        show_inactive = self.request.GET.get('show_inactive')
        if not show_inactive:
            qs = qs.filter(is_active=True)
        return qs.order_by('default_due_month', 'default_due_day', 'title')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['frequencies'] = ComplianceTaskTemplate.Frequency.choices
        ctx['current_frequency'] = self.request.GET.get('frequency', '')
        return ctx


class TemplateCreateView(OrganizationViewMixin, CreateView):
    model = ComplianceTaskTemplate
    form_class = ComplianceTaskTemplateForm
    template_name = 'compliance/template_form.html'

    def get_success_url(self):
        return reverse('compliance:template_list')


class TemplateUpdateView(OrganizationViewMixin, UpdateView):
    model = ComplianceTaskTemplate
    form_class = ComplianceTaskTemplateForm
    template_name = 'compliance/template_form.html'

    def get_success_url(self):
        return reverse('compliance:template_list')


class TemplateDeleteView(OrganizationViewMixin, DeleteView):
    model = ComplianceTaskTemplate
    success_url = reverse_lazy('compliance:template_list')
    template_name = 'compliance/template_confirm_delete.html'

    def form_valid(self, form):
        self.object.delete(user=self.request.user)
        messages.success(self.request, 'Template deleted.')
        if self.request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect(self.success_url)


# ============ Task Generation (Phase 3) ============

class GenerateTasksView(OrganizationViewMixin, View):
    def post(self, request):
        year = int(request.POST.get('year', timezone.now().year))
        regenerate = request.POST.get('regenerate') == 'on'
        created, skipped = generate_tasks(request.organization, year, regenerate=regenerate)
        messages.success(request, f'Generated {created} tasks for {year}. Skipped {skipped}.')
        return redirect(reverse('compliance:task_list') + f'?year={year}')


# ============ Task CRUD (Phase 3) ============

class TaskListView(OrganizationViewMixin, ListView):
    model = ComplianceTask
    template_name = 'compliance/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related('template', 'completed_by')
        year = self.request.GET.get('year')
        if year:
            qs = qs.filter(year=int(year))
        month = self.request.GET.get('month')
        if month:
            qs = qs.filter(month=int(month))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        tag = self.request.GET.get('tag')
        if tag:
            qs = qs.filter(tags__icontains=tag)
        return qs.order_by('due_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = ComplianceTask.Status.choices
        ctx['current_year'] = self.request.GET.get('year', str(timezone.now().year))
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_tag'] = self.request.GET.get('tag', '')
        return ctx

    def get_template_names(self):
        if self.request.htmx and not self.request.htmx.boosted:
            return ['compliance/partials/task_list_content.html']
        return [self.template_name]


class TaskDetailView(OrganizationViewMixin, DetailView):
    model = ComplianceTask
    template_name = 'compliance/task_detail.html'
    context_object_name = 'task'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'template', 'completed_by'
        ).prefetch_related('evidence_items', 'audit_logs', 'audit_logs__user')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['evidence_form'] = EvidenceUploadForm()
        ctx['statuses'] = ComplianceTask.Status.choices
        return ctx


class TaskCreateView(OrganizationViewMixin, CreateView):
    model = ComplianceTask
    form_class = ComplianceTaskForm
    template_name = 'compliance/task_form.html'

    def form_valid(self, form):
        form.instance.year = form.instance.due_date.year
        form.instance.month = form.instance.due_date.month
        response = super().form_valid(form)
        log_action(
            self.object, ComplianceAuditLog.ActionType.TASK_CREATED,
            self.request.user,
            new_value={'title': self.object.title, 'due_date': str(self.object.due_date)},
            description=f'Task created: {self.object.title}',
        )
        messages.success(self.request, 'Task created.')
        return response

    def get_success_url(self):
        return reverse('compliance:task_detail', kwargs={'pk': self.object.pk})


class TaskUpdateView(OrganizationViewMixin, UpdateView):
    model = ComplianceTask
    form_class = ComplianceTaskForm
    template_name = 'compliance/task_form.html'

    def form_valid(self, form):
        old_values = {}
        new_values = {}
        for field in form.changed_data:
            old_values[field] = str(form.initial.get(field, ''))
            new_values[field] = str(form.cleaned_data.get(field, ''))

        response = super().form_valid(form)

        if old_values:
            log_action(
                self.object, ComplianceAuditLog.ActionType.TASK_EDIT,
                self.request.user,
                old_value=old_values, new_value=new_values,
                description=f"Task updated: {', '.join(new_values.keys())}",
            )
        messages.success(self.request, 'Task updated.')
        return response

    def get_success_url(self):
        return reverse('compliance:task_detail', kwargs={'pk': self.object.pk})


class TaskDeleteView(OrganizationViewMixin, DeleteView):
    model = ComplianceTask
    success_url = reverse_lazy('compliance:task_list')
    template_name = 'compliance/task_confirm_delete.html'

    def form_valid(self, form):
        self.object.delete(user=self.request.user)
        messages.success(self.request, 'Task deleted.')
        if self.request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect(self.success_url)


class TaskStatusUpdateView(OrganizationViewMixin, View):
    """HTMX view to update task status and redirect to list."""

    def post(self, request, pk):
        task = get_object_or_404(
            ComplianceTask.objects.filter(organization=request.organization), pk=pk
        )
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')

        old_status = task.status
        task.status = new_status

        if new_status == ComplianceTask.Status.COMPLETED:
            task.completed_at = timezone.now()
            task.completed_by = request.user
        elif old_status == ComplianceTask.Status.COMPLETED:
            task.completed_at = None
            task.completed_by = None

        if notes and notes != task.notes:
            log_action(
                task, ComplianceAuditLog.ActionType.NOTE_EDIT,
                request.user,
                old_value={'notes': task.notes},
                new_value={'notes': notes},
                description='Notes updated',
            )
            task.notes = notes

        task.save()

        log_action(
            task, ComplianceAuditLog.ActionType.STATUS_CHANGE,
            request.user,
            old_value={'status': old_status},
            new_value={'status': new_status},
            description=f'Status changed from {old_status} to {new_status}',
        )

        messages.success(request, f'Task "{task.title}" updated.')

        redirect_url = reverse('compliance:task_list') + f'?year={task.year}'
        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Redirect': redirect_url})
        return redirect(redirect_url)


# ============ Evidence (Phase 4) ============

class EvidenceUploadView(OrganizationViewMixin, View):
    def post(self, request, pk):
        task = get_object_or_404(
            ComplianceTask.objects.filter(organization=request.organization), pk=pk
        )
        form = EvidenceUploadForm(request.POST, request.FILES, organization=request.organization)
        
        toast_message = None
        toast_type = 'info'

        if form.is_valid():
            evidence = form.save(commit=False)
            evidence.task = task
            evidence.organization = request.organization
            evidence.uploaded_by = request.user
            evidence.created_by = request.user
            
            # Get file details from cleaned_data
            file_obj = form.cleaned_data.get('file')
            if file_obj:
                evidence.original_filename = file_obj.name
                evidence.mime_type = getattr(file_obj, 'content_type', '')
                evidence.size_bytes = file_obj.size
            elif evidence.external_link:
                evidence.original_filename = '' # Clear if link
            
            evidence.save()

            log_action(
                task, ComplianceAuditLog.ActionType.EVIDENCE_ADD,
                request.user,
                new_value={'filename': evidence.original_filename, 'external_link': evidence.external_link},
                description=f'Evidence added: {evidence.original_filename or evidence.external_link}',
            )
            
            toast_message = 'Evidence uploaded successfully.'
            toast_type = 'success'
            messages.success(request, toast_message)
            # Clear form on success
            form = EvidenceUploadForm()
        else:
            # Add field errors to message for better debugging
            error_details = []
            for field, errors in form.errors.items():
                error_details.append(f"{field}: {', '.join(errors)}")
            
            toast_message = f"Upload failed. {'; '.join(error_details)}"
            if not error_details:
                toast_message = "Upload failed. Please provide a file or an external link."
            
            toast_type = 'error'
            messages.error(request, toast_message)

        if request.htmx:
            evidence_items = task.evidence_items.all()
            html = render_to_string(
                'compliance/partials/evidence_list.html',
                {'task': task, 'evidence_items': evidence_items, 'evidence_form': form},
                request=request,
            )
            response = HttpResponse(html)
            
            # Trigger toast via HTMX header
            if toast_message:
                import json
                trigger_data = {
                    'toast': {
                        'message': toast_message,
                        'type': toast_type
                    }
                }
                response['HX-Trigger'] = json.dumps(trigger_data)
            
            return response
            
        return redirect('compliance:task_detail', pk=pk)


class EvidencePasteUploadView(OrganizationViewMixin, View):
    """Handle image blobs pasted from the clipboard."""

    def post(self, request, pk):
        task = get_object_or_404(
            ComplianceTask.objects.filter(organization=request.organization), pk=pk
        )

        if 'image' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No image provided'}, status=400)

        image_file = request.FILES['image']
        description = request.POST.get('description', 'Pasted image evidence')

        # Create evidence record
        evidence = ComplianceEvidence.objects.create(
            task=task,
            organization=request.organization,
            file=image_file,
            original_filename=f"pasted_image_{timezone.now().strftime('%Y%m%d_%H%M%S')}.png",
            mime_type=image_file.content_type or 'image/png',
            size_bytes=image_file.size,
            description=description,
            uploaded_by=request.user,
            created_by=request.user,
        )

        log_action(
            task, ComplianceAuditLog.ActionType.EVIDENCE_ADD,
            request.user,
            new_value={'filename': evidence.original_filename},
            description=f'Evidence pasted: {evidence.original_filename}',
        )

        return JsonResponse({
            'success': True,
            'filename': evidence.original_filename,
        })


class EvidenceDeleteView(OrganizationViewMixin, View):
    def post(self, request, pk, evidence_pk):
        task = get_object_or_404(
            ComplianceTask.objects.filter(organization=request.organization), pk=pk
        )
        evidence = get_object_or_404(task.evidence_items, pk=evidence_pk)

        log_action(
            task, ComplianceAuditLog.ActionType.EVIDENCE_REMOVE,
            request.user,
            old_value={'filename': evidence.original_filename},
            description=f'Evidence removed: {evidence.original_filename or evidence.external_link}',
        )

        if evidence.file:
            evidence.file.delete(save=False)
        evidence.delete()
        
        msg = 'Evidence removed.'
        messages.success(request, msg)

        if request.htmx:
            evidence_items = task.evidence_items.all()
            html = render_to_string(
                'compliance/partials/evidence_list.html',
                {'task': task, 'evidence_items': evidence_items, 'evidence_form': EvidenceUploadForm()},
                request=request,
            )
            response = HttpResponse(html)
            import json
            response['HX-Trigger'] = json.dumps({'toast': {'message': msg, 'type': 'success'}})
            return response
        return redirect('compliance:task_detail', pk=pk)


class EvidenceDownloadView(OrganizationViewMixin, View):
    def get(self, request, pk, evidence_pk):
        task = get_object_or_404(
            ComplianceTask.objects.filter(organization=request.organization), pk=pk
        )
        evidence = get_object_or_404(task.evidence_items, pk=evidence_pk)
        if not evidence.file:
            messages.error(request, 'No file to download.')
            return redirect('compliance:task_detail', pk=pk)
        from django.http import FileResponse
        response = FileResponse(evidence.file.open('rb'), content_type=evidence.mime_type or 'application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{evidence.original_filename}"'
        return response


# ============ Calendar (Phase 5) ============

class CalendarMonthView(OrganizationViewMixin, TemplateView):
    template_name = 'compliance/calendar.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now().date()
        year = int(self.request.GET.get('year', now.year))
        month = int(self.request.GET.get('month', now.month))

        # Clamp month
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1

        first_day = date(year, month, 1)
        _, num_days = cal.monthrange(year, month)
        last_day = date(year, month, num_days)

        tasks = ComplianceTask.objects.filter(
            organization=self.request.organization,
            due_date__gte=first_day,
            due_date__lte=last_day,
        ).annotate(evidence_count=Count('evidence_items')).order_by('due_date')

        # Group tasks by day
        days = {}
        for d in range(1, num_days + 1):
            days[d] = []
        for task in tasks:
            days[task.due_date.day].append(task)

        # Build calendar weeks (starting Monday)
        weeks = cal.Calendar(firstweekday=6).monthdayscalendar(year, month)
        calendar_weeks = []
        for week in weeks:
            week_data = []
            for day in week:
                if day == 0:
                    week_data.append({'day': 0, 'tasks': [], 'is_today': False})
                else:
                    d = date(year, month, day)
                    week_data.append({
                        'day': day,
                        'tasks': days.get(day, []),
                        'is_today': d == now,
                        'date': d,
                    })
            calendar_weeks.append(week_data)

        # Nav
        prev_month = month - 1
        prev_year = year
        if prev_month < 1:
            prev_month = 12
            prev_year -= 1
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year += 1

        ctx.update({
            'year': year,
            'month': month,
            'month_name': first_day.strftime('%B'),
            'calendar_weeks': calendar_weeks,
            'prev_year': prev_year,
            'prev_month': prev_month,
            'next_year': next_year,
            'next_month': next_month,
            'today': now,
        })
        return ctx

    def get_template_names(self):
        if self.request.htmx and not self.request.htmx.boosted:
            return ['compliance/partials/calendar_month.html']
        return [self.template_name]


class CalendarYearView(OrganizationViewMixin, TemplateView):
    template_name = 'compliance/calendar_year.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        year = int(self.request.GET.get('year', timezone.now().year))
        tasks = ComplianceTask.objects.filter(
            organization=self.request.organization, year=year
        ).order_by('due_date')

        months = []
        for m in range(1, 13):
            month_tasks = [t for t in tasks if t.month == m]
            completed = sum(1 for t in month_tasks if t.status == ComplianceTask.Status.COMPLETED)
            months.append({
                'number': m,
                'name': date(year, m, 1).strftime('%B'),
                'tasks': month_tasks,
                'total': len(month_tasks),
                'completed': completed,
            })

        ctx.update({'year': year, 'months': months})
        return ctx


# ============ Documents (Phase 6) ============

class DocumentListView(OrganizationViewMixin, ListView):
    model = ComplianceDocument
    template_name = 'compliance/document_list.html'
    context_object_name = 'documents'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = ComplianceDocumentForm()
        return ctx


class DocumentUploadView(OrganizationViewMixin, CreateView):
    model = ComplianceDocument
    form_class = ComplianceDocumentForm
    template_name = 'compliance/document_list.html'

    def form_valid(self, form):
        doc = form.save(commit=False)
        doc.organization = self.request.organization
        doc.created_by = self.request.user
        if doc.file:
            doc.original_filename = doc.file.name
            doc.file_type = doc.file.content_type or ''
            doc.file_size = doc.file.size
        doc.save()
        messages.success(self.request, 'Document uploaded.')
        return redirect('compliance:document_list')


class DocumentDownloadView(OrganizationViewMixin, View):
    def get(self, request, pk):
        doc = get_object_or_404(
            ComplianceDocument.objects.filter(organization=request.organization), pk=pk
        )
        from django.http import FileResponse
        response = FileResponse(doc.file.open('rb'), content_type=doc.file_type or 'application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{doc.original_filename or doc.name}"'
        return response


class DocumentDeleteView(OrganizationViewMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(
            ComplianceDocument.objects.filter(organization=request.organization), pk=pk
        )
        doc.delete(user=request.user)
        messages.success(request, 'Document deleted.')
        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect('compliance:document_list')


# ============ SEC News (Phase 6) ============

class SECNewsListView(OrganizationViewMixin, ListView):
    model = SECNewsItem
    template_name = 'compliance/news_list.html'
    context_object_name = 'news_items'
    paginate_by = 50

    def get_queryset(self):
        qs = SECNewsItem.objects.filter(organization=self.request.organization)
        unread_only = self.request.GET.get('unread')
        if unread_only:
            qs = qs.filter(is_read=False)
        return qs.order_by('-published_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = SECNewsItem.objects.filter(
            organization=self.request.organization, is_read=False
        ).count()
        return ctx


class SECNewsRefreshView(OrganizationViewMixin, View):
    def post(self, request):
        from .services.rss import fetch_all_feeds
        items = fetch_all_feeds(filter_relevant=False)
        created = 0
        for item in items:
            _, was_created = SECNewsItem.objects.get_or_create(
                organization=request.organization,
                guid=item['guid'],
                defaults={
                    'title': item['title'],
                    'link': item['link'],
                    'description': item['description'],
                    'published_at': item['published_at'],
                    'source': item['source'],
                    'is_relevant': item.get('is_relevant', True),
                },
            )
            if was_created:
                created += 1
        messages.success(request, f'Fetched {created} new SEC news items.')
        return redirect('compliance:news_list')


class SECNewsMarkReadView(OrganizationViewMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(
            SECNewsItem.objects.filter(organization=request.organization), pk=pk
        )
        item.is_read = not item.is_read
        item.save(update_fields=['is_read'])
        
        msg = f"News item marked as {'read' if item.is_read else 'unread'}."
        
        if request.htmx:
            html = render_to_string(
                'compliance/partials/news_item.html',
                {'item': item},
                request=request,
            )
            response = HttpResponse(html)
            import json
            response['HX-Trigger'] = json.dumps({'toast': {'message': msg, 'type': 'info'}})
            return response
        return redirect('compliance:news_list')


class SECNewsMarkAllReadView(OrganizationViewMixin, View):
    def post(self, request):
        SECNewsItem.objects.filter(
            organization=request.organization, is_read=False
        ).update(is_read=True)
        messages.success(request, 'All news marked as read.')
        return redirect('compliance:news_list')


# ============ Exports (Phase 7) ============

class ExportCSVView(OrganizationViewMixin, View):
    def get(self, request, year):
        from .services.exports import export_csv
        csv_content = export_csv(request.organization, year)
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=bireme_compliance_{year}.csv'
        return response


class ExportZIPView(OrganizationViewMixin, View):
    def get(self, request, year):
        from .services.exports import export_zip
        zip_content = export_zip(request.organization, year)
        response = HttpResponse(zip_content, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename=bireme_compliance_{year}_export.zip'
        return response


class ExportPDFView(OrganizationViewMixin, View):
    def get(self, request, year):
        from .services.exports import generate_audit_pdf
        pdf_content = generate_audit_pdf(request.organization, year, request.user)
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=compliance_audit_report_{year}.pdf'
        return response


# ============ Surveys & Certifications ============

class SurveyTemplateListView(OrganizationViewMixin, ListView):
    model = SurveyTemplate
    template_name = 'compliance/surveys/template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return SurveyTemplate.objects.filter(organization=self.request.organization)


class SurveyTemplateDetailView(OrganizationViewMixin, DetailView):
    model = SurveyTemplate
    template_name = 'compliance/surveys/template_detail.html'
    context_object_name = 'template'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['versions'] = self.object.versions.all().prefetch_related('questions')
        return ctx


class SurveyPublishVersionView(OrganizationViewMixin, View):
    def post(self, request, pk):
        template = get_object_or_404(SurveyTemplate.objects.filter(organization=request.organization), pk=pk)
        # In a real app, we'd take a draft and publish it. 
        # For this prototype, we'll just mark the latest version as published.
        version = template.versions.order_by('-version_number').first()
        if version:
            version.is_published = True
            version.effective_date = timezone.now().date()
            version.save()
            messages.success(request, f"Published Version {version.version_number} of {template.name}")
        return redirect('compliance:survey_template_detail', pk=pk)


class SurveyDashboardView(OrganizationViewMixin, TemplateView):
    template_name = 'compliance/surveys/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.organization
        assignments = SurveyAssignment.objects.filter(organization=org)
        
        ctx.update({
            'total_assignments': assignments.count(),
            'pending_review': assignments.filter(status=SurveyAssignment.Status.SUBMITTED).count(),
            'overdue_count': assignments.filter(status=SurveyAssignment.Status.OVERDUE).count(),
            'recent_assignments': assignments.order_by('-assigned_at')[:10],
            'active_templates': SurveyTemplate.objects.filter(organization=org, is_active=True).count(),
            'open_exceptions': SurveyException.objects.filter(organization=org, status=SurveyException.Status.OPEN).count()
        })
        return ctx


class MySurveysListView(OrganizationViewMixin, ListView):
    model = SurveyAssignment
    template_name = 'compliance/surveys/my_surveys.html'
    context_object_name = 'assignments'

    def get_queryset(self):
        return SurveyAssignment.objects.filter(
            user=self.request.user,
            organization=self.request.organization
        ).order_by('-due_date')


class SurveyAssignPeriodicView(OrganizationViewMixin, View):
    def post(self, request):
        year = int(request.POST.get('year', timezone.now().year))
        quarter = request.POST.get('quarter')
        if quarter:
            quarter = int(quarter)
        else:
            quarter = None
            
        created, skipped = assign_periodic_surveys(request.organization, year, quarter)
        messages.success(request, f"Assigned {created} surveys. Skipped {skipped} duplicates.")
        return redirect('compliance:survey_dashboard')


class SurveyCompleteView(OrganizationViewMixin, View):
    template_name = 'compliance/surveys/survey_form.html'

    def get(self, request, pk):
        assignment = get_object_or_404(
            SurveyAssignment.objects.filter(user=request.user, organization=request.organization), 
            pk=pk
        )
        if assignment.status not in [SurveyAssignment.Status.NOT_STARTED, SurveyAssignment.Status.IN_PROGRESS]:
            messages.warning(request, "This survey has already been submitted or is no longer editable.")
            return redirect('compliance:my_surveys')
            
        form = SurveyCompleteForm(version=assignment.version)
        return self._render(request, assignment, form)

    def post(self, request, pk):
        assignment = get_object_or_404(
            SurveyAssignment.objects.filter(user=request.user, organization=request.organization), 
            pk=pk
        )
        form = SurveyCompleteForm(request.POST, request.FILES, version=assignment.version)
        if form.is_valid():
            process_survey_submission(assignment, form.cleaned_data, request.user, request.FILES)
            messages.success(request, "Certification submitted successfully.")
            return redirect('compliance:my_surveys')
            
        return self._render(request, assignment, form)

    def _render(self, request, assignment, form):
        from django.template.response import TemplateResponse
        return TemplateResponse(request, self.template_name, {
            'assignment': assignment,
            'form': form,
            'version': assignment.version,
            'template': assignment.version.template
        })


class SurveyReviewView(OrganizationViewMixin, View):
    template_name = 'compliance/surveys/review_detail.html'

    def get(self, request, pk):
        # Only admins can review
        if request.membership.role != 'admin':
            return HttpResponse(status=403)
            
        assignment = get_object_or_404(
            SurveyAssignment.objects.filter(organization=request.organization), 
            pk=pk
        )
        response = getattr(assignment, 'response', None)
        answers = response.answers.all().select_related('question') if response else []
        
        return self._render(request, assignment, response, answers)

    def post(self, request, pk):
        if request.membership.role != 'admin':
            return HttpResponse(status=403)
            
        assignment = get_object_or_404(
            SurveyAssignment.objects.filter(organization=request.organization), 
            pk=pk
        )
        action = request.POST.get('action')
        notes = request.POST.get('review_notes', '')

        if action == 'approve':
            assignment.status = SurveyAssignment.Status.APPROVED
        elif action == 'reject':
            assignment.status = SurveyAssignment.Status.REJECTED
            
        assignment.reviewed_at = timezone.now()
        assignment.reviewed_by = request.user
        assignment.save()
        
        messages.success(request, f"Survey {action}d.")
        return redirect('compliance:survey_dashboard')

    def _render(self, request, assignment, response, answers):
        from django.template.response import TemplateResponse
        return TemplateResponse(request, self.template_name, {
            'assignment': assignment,
            'response': response,
            'answers': answers,
        })


class SurveyExceptionListView(OrganizationViewMixin, ListView):
    model = SurveyException
    template_name = 'compliance/surveys/exception_list.html'
    context_object_name = 'exceptions'

    def get_queryset(self):
        return SurveyException.objects.filter(organization=self.request.organization).select_related('assignment', 'assignment__user')


class ExportSurveyCSVView(OrganizationViewMixin, View):
    def get(self, request, year):
        from .services.exports import export_surveys_csv
        csv_content = export_surveys_csv(request.organization, year)
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=compliance_surveys_{year}.csv'
        return response
