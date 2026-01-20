"""
Views for Todo management.
"""
from django.contrib import messages
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from core.mixins import OrganizationViewMixin
from apps.companies.models import Company
from .models import Todo, TodoCategory, WatchlistQuickAdd
from .forms import TodoForm, QuickTodoForm, InvestorLetterTodoForm, WatchlistQuickAddFormSet, CompleteWithNoteForm, QuarterlySettingsForm
from apps.notes.models import Note


class TodoListView(OrganizationViewMixin, ListView):
    """Main todo list view - dedicated todo section."""
    model = Todo
    template_name = 'todos/todo_list.html'
    context_object_name = 'todos'
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'company', 'category', 'created_by', 'completed_by'
        )

        # Filter by category (slug or pk)
        category_filter = self.request.GET.get('category')
        if category_filter:
            # Try to filter by slug first, then by category_type for backward compatibility
            if category_filter.isdigit():
                qs = qs.filter(category_id=category_filter)
            else:
                # Check if it's a category slug or a legacy category_type
                category = TodoCategory.objects.filter(
                    organization=self.request.organization,
                    slug=category_filter
                ).first()
                if category:
                    qs = qs.filter(category=category)
                else:
                    # Fallback to category_type for backward compatibility
                    qs = qs.filter(category__category_type=category_filter)

        # Filter by completion
        status = self.request.GET.get('status')
        if status == 'pending':
            qs = qs.pending()
        elif status == 'completed':
            qs = qs.completed()

        # Filter by todo type
        todo_type = self.request.GET.get('type')
        if todo_type:
            qs = qs.filter(todo_type=todo_type)

        # Filter by company
        company_slug = self.request.GET.get('company')
        if company_slug:
            qs = qs.filter(company__slug=company_slug)

        # Filter by quarter
        quarter = self.request.GET.get('quarter')
        if quarter:
            qs = qs.filter(quarter=quarter)

        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            qs = qs.filter(priority=priority)

        # Filter by age
        age = self.request.GET.get('age')
        if age:
            from datetime import timedelta
            from django.utils import timezone
            now = timezone.now()

            if age == 'today':
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                qs = qs.filter(created_at__gte=start)
            elif age == 'week':
                start = now - timedelta(days=7)
                qs = qs.filter(created_at__gte=start)
            elif age == 'month':
                start = now - timedelta(days=30)
                qs = qs.filter(created_at__gte=start)
            elif age == 'older':
                start = now - timedelta(days=30)
                qs = qs.filter(created_at__lt=start)

        return qs.order_by('is_completed', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all categories with pending counts
        categories = TodoCategory.objects.filter(
            organization=self.request.organization
        ).annotate(
            pending_count=models.Count(
                'todos',
                filter=models.Q(todos__is_deleted=False, todos__is_completed=False)
            )
        ).order_by('order', 'name')
        context['categories'] = categories

        context['todo_types'] = Todo.TodoType.choices
        context['current_category'] = self.request.GET.get('category', '')
        context['current_status'] = self.request.GET.get('status', 'pending')
        context['current_type'] = self.request.GET.get('type', '')
        context['current_company'] = self.request.GET.get('company', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['current_age'] = self.request.GET.get('age', '')
        context['priorities'] = Todo.Priority.choices

        # Stats for summary
        org_todos = Todo.objects.filter(organization=self.request.organization)
        context['pending_count'] = org_todos.pending().count()
        context['completed_count'] = org_todos.completed().count()

        # Legacy stats for backward compatibility (can be removed later)
        context['maintenance_pending'] = org_todos.pending().maintenance().count()
        context['idea_generation_pending'] = org_todos.pending().idea_generation().count()
        context['marketing_pending'] = org_todos.pending().marketing().count()

        # Section-based todos for the default view (pending only, grouped by category)
        # Only show sections when no filters are applied (except default pending status)
        show_sections = (
            not self.request.GET.get('category') and
            self.request.GET.get('status', 'pending') == 'pending' and
            not self.request.GET.get('priority') and
            not self.request.GET.get('age')
        )
        if show_sections:
            base_qs = org_todos.pending().select_related('company', 'category', 'created_by')
            # Build category sections dynamically
            category_sections = []
            for category in categories:
                todos = base_qs.filter(category=category).order_by('-created_at')[:20]
                if todos.exists() or category.pending_count > 0:
                    category_sections.append({
                        'category': category,
                        'todos': todos,
                        'count': category.pending_count,
                    })
            context['category_sections'] = category_sections

            # Also include uncategorized todos
            uncategorized_todos = base_qs.filter(category__isnull=True).order_by('-created_at')[:20]
            if uncategorized_todos.exists():
                context['uncategorized_todos'] = uncategorized_todos

        context['show_sections'] = show_sections

        return context

    def get_template_names(self):
        # Only return partial for targeted HTMX requests (not boosted navigation)
        if self.request.htmx and not self.request.htmx.boosted:
            return ['todos/partials/todo_list_content.html']
        return [self.template_name]


class TodoDetailView(OrganizationViewMixin, DetailView):
    """Todo detail view."""
    model = Todo
    template_name = 'todos/todo_detail.html'
    context_object_name = 'todo'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'company', 'category', 'created_by', 'completed_by', 'completion_note'
        ).prefetch_related('watchlist_additions')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.todo_type == Todo.TodoType.INVESTOR_LETTER:
            context['watchlist_additions'] = self.object.watchlist_additions.filter(
                is_processed=False
            )
        return context


class TodoCreateView(OrganizationViewMixin, CreateView):
    """Create a new custom todo."""
    model = Todo
    form_class = TodoForm
    template_name = 'todos/todo_form.html'

    def get_initial(self):
        initial = super().get_initial()
        company_slug = self.request.GET.get('company')
        if company_slug:
            try:
                company = Company.objects.get(
                    organization=self.request.organization,
                    slug=company_slug
                )
                initial['company'] = company
                # Auto-select category based on company status
                if company.status == Company.Status.PORTFOLIO:
                    cat = TodoCategory.objects.filter(
                        organization=self.request.organization,
                        category_type=TodoCategory.CategoryType.MAINTENANCE
                    ).first()
                else:
                    cat = TodoCategory.objects.filter(
                        organization=self.request.organization,
                        category_type=TodoCategory.CategoryType.IDEA_GENERATION
                    ).first()
                if cat:
                    initial['category'] = cat
            except Company.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        form.instance.organization = self.request.organization
        form.instance.created_by = self.request.user
        form.instance.todo_type = Todo.TodoType.CUSTOM
        response = super().form_valid(form)
        messages.success(self.request, 'Todo created.')
        return response

    def get_success_url(self):
        if self.request.GET.get('company') and self.object.company:
            return self.object.company.get_absolute_url()
        return reverse('todos:list')


class TodoUpdateView(OrganizationViewMixin, UpdateView):
    """Update a todo."""
    model = Todo
    form_class = TodoForm
    template_name = 'todos/todo_form.html'

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'Todo updated.')
        return response

    def get_success_url(self):
        return reverse('todos:detail', kwargs={'pk': self.object.pk})


class TodoDeleteView(OrganizationViewMixin, DeleteView):
    """Soft delete a todo."""
    model = Todo
    success_url = reverse_lazy('todos:list')

    def form_valid(self, form):
        self.object.delete(user=self.request.user)
        messages.success(self.request, 'Todo deleted.')
        if self.request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
        return redirect(self.success_url)


class TodoToggleCompleteView(OrganizationViewMixin, View):
    """HTMX view to toggle todo completion status."""

    def post(self, request, pk):
        todo = get_object_or_404(
            Todo.objects.filter(organization=request.organization),
            pk=pk
        )

        if todo.is_completed:
            todo.mark_incomplete()
        else:
            todo.mark_complete(user=request.user)

        html = render_to_string(
            'todos/partials/todo_card.html',
            {'todo': todo},
            request=request
        )
        return HttpResponse(html)


class QuickTodoCreateView(OrganizationViewMixin, View):
    """HTMX view for quick todo creation from company page."""

    def post(self, request, company_slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=company_slug
        )

        form = QuickTodoForm(request.POST, organization=request.organization)
        if form.is_valid():
            todo = form.save(commit=False)
            todo.organization = request.organization
            todo.company = company
            todo.created_by = request.user
            todo.todo_type = Todo.TodoType.CUSTOM

            # Auto-select category based on company status
            if company.status == Company.Status.PORTFOLIO:
                todo.category = TodoCategory.objects.filter(
                    organization=request.organization,
                    category_type=TodoCategory.CategoryType.MAINTENANCE
                ).first()
            else:
                todo.category = TodoCategory.objects.filter(
                    organization=request.organization,
                    category_type=TodoCategory.CategoryType.IDEA_GENERATION
                ).first()

            todo.save()

            html = render_to_string(
                'todos/partials/todo_card.html',
                {'todo': todo},
                request=request
            )
            return HttpResponse(html)

        return HttpResponse(status=400)


class InvestorLetterTodoUpdateView(OrganizationViewMixin, UpdateView):
    """Special view for investor letter todos with embedded notes."""
    model = Todo
    form_class = InvestorLetterTodoForm
    template_name = 'todos/investor_letter_form.html'

    def get_queryset(self):
        return super().get_queryset().filter(
            todo_type=Todo.TodoType.INVESTOR_LETTER
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['watchlist_formset'] = WatchlistQuickAddFormSet(
                self.request.POST,
                instance=self.object
            )
        else:
            context['watchlist_formset'] = WatchlistQuickAddFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        watchlist_formset = context['watchlist_formset']

        form.instance.updated_by = self.request.user

        if watchlist_formset.is_valid():
            response = super().form_valid(form)
            watchlist_formset.save()
            messages.success(self.request, 'Investor letter review updated.')
            return response
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('todos:detail', kwargs={'pk': self.object.pk})


class ProcessWatchlistQuickAddView(OrganizationViewMixin, View):
    """Process a single watchlist quick-add into a full Company."""

    def post(self, request, pk):
        quick_add = get_object_or_404(
            WatchlistQuickAdd.objects.filter(
                todo__organization=request.organization,
                is_processed=False
            ),
            pk=pk
        )

        # Create the company
        from apps.companies.models import CompanyTicker
        company = Company.objects.create(
            organization=request.organization,
            name=quick_add.ticker.upper(),
            status=Company.Status.WATCHLIST,
            alert_price=quick_add.alert_price,
            alert_price_reason=quick_add.note,
            thesis=quick_add.note,
            created_by=request.user
        )

        # Create ticker
        CompanyTicker.objects.create(
            company=company,
            symbol=quick_add.ticker.upper(),
            is_primary=True
        )

        # Mark as processed
        quick_add.is_processed = True
        quick_add.created_company = company
        quick_add.save()

        messages.success(request, f'{quick_add.ticker.upper()} added to watchlist.')

        if request.htmx:
            html = render_to_string(
                'todos/partials/quick_add_processed.html',
                {'quick_add': quick_add, 'company': company},
                request=request
            )
            return HttpResponse(html)

        return redirect('todos:detail', pk=quick_add.todo.pk)


class CompanyTodosPartialView(OrganizationViewMixin, View):
    """HTMX partial view for todos on company detail page."""

    def get(self, request, company_slug):
        company = get_object_or_404(
            Company.objects.filter(organization=request.organization),
            slug=company_slug
        )

        todos = Todo.objects.filter(
            organization=request.organization,
            company=company
        ).select_related('category').order_by('is_completed', '-created_at')[:10]

        html = render_to_string(
            'todos/partials/company_todos.html',
            {'todos': todos, 'company': company},
            request=request
        )
        return HttpResponse(html)


class CompleteWithNoteView(OrganizationViewMixin, CreateView):
    """Complete a todo by creating an attached note as evidence."""
    model = Note
    form_class = CompleteWithNoteForm
    template_name = 'todos/complete_with_note.html'

    def dispatch(self, request, *args, **kwargs):
        self.todo = get_object_or_404(
            Todo.objects.filter(organization=request.organization),
            pk=kwargs['pk']
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['todo'] = self.todo
        return context

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill title with todo title
        initial['title'] = f"Completed: {self.todo.title}"
        return initial

    def form_valid(self, form):
        # Create the note
        note = form.save(commit=False)
        note.organization = self.request.organization
        note.created_by = self.request.user

        # Use todo's company if available
        if self.todo.company:
            note.company = self.todo.company
        else:
            # If no company on todo, we need a company for the note
            # This shouldn't happen often, but handle gracefully
            messages.error(self.request, 'Cannot create note without a company.')
            return self.form_invalid(form)

        note.save()

        # Mark the todo complete with the note attached
        self.todo.mark_complete(user=self.request.user, note=note)

        messages.success(
            self.request,
            f'Todo completed with note: "{note.title[:50]}"'
        )

        return redirect(self.get_success_url())

    def get_success_url(self):
        # Go to the todo detail to see the completion note
        return reverse('todos:detail', kwargs={'pk': self.todo.pk})


class TodoBulkDeleteView(OrganizationViewMixin, View):
    """Handle bulk deletion of todos."""

    def post(self, request):
        todo_ids = request.POST.getlist('todo_ids')

        if not todo_ids:
            messages.warning(request, 'No todos selected.')
            return redirect('todos:list')

        # Filter to only todos in the user's organization
        todos = Todo.objects.filter(
            organization=request.organization,
            pk__in=todo_ids
        )

        count = todos.count()

        # Soft delete each todo
        for todo in todos:
            todo.delete(user=request.user)

        messages.success(request, f'Deleted {count} todo{"s" if count != 1 else ""}.')

        if request.htmx:
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return redirect('todos:list')


class QuarterlySettingsView(OrganizationViewMixin, View):
    """View for managing quarterly todo generation settings."""

    def get(self, request):
        """Return the settings form as HTML partial."""
        form = QuarterlySettingsForm(organization=request.organization)
        html = render_to_string(
            'todos/partials/quarterly_settings_form.html',
            {'form': form},
            request=request
        )
        return HttpResponse(html)

    def post(self, request):
        """Save quarterly settings."""
        form = QuarterlySettingsForm(request.POST, organization=request.organization)

        if form.is_valid():
            # Build the statuses list
            statuses = []
            if form.cleaned_data['portfolio_enabled']:
                statuses.append('portfolio')
            if form.cleaned_data['on_deck_enabled']:
                statuses.append('on_deck')

            # Update organization settings
            request.organization.set_quarterly_settings(
                enabled=form.cleaned_data['enabled'],
                days_after_quarter=form.cleaned_data['days_after_quarter'],
                statuses=statuses,
                investor_letter_enabled=form.cleaned_data['investor_letter_enabled']
            )

            messages.success(request, 'Todo generation settings saved.')

            if request.htmx:
                return HttpResponse(
                    status=204,
                    headers={'HX-Trigger': 'settingsSaved'}
                )

            return redirect('todos:list')

        # Form invalid - return form with errors
        html = render_to_string(
            'todos/partials/quarterly_settings_form.html',
            {'form': form},
            request=request
        )
        return HttpResponse(html)


# ============================================
# Category Management Views
# ============================================

class CategoryListView(OrganizationViewMixin, ListView):
    """List all todo categories for the organization."""
    model = TodoCategory
    template_name = 'todos/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return TodoCategory.objects.filter(
            organization=self.request.organization
        ).annotate(
            todo_count=models.Count('todos', filter=models.Q(todos__is_deleted=False))
        ).order_by('order', 'name')


class CategoryCreateView(OrganizationViewMixin, CreateView):
    """Create a new todo category."""
    model = TodoCategory
    template_name = 'todos/category_form.html'
    fields = ['name', 'color', 'icon', 'order']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('organization', None)  # Remove org kwarg - auto-generated form doesn't accept it
        return kwargs

    def form_valid(self, form):
        form.instance.organization = self.request.organization
        form.instance.is_system = False  # User-created categories are not system categories
        # Auto-generate slug from name
        base_slug = slugify(form.instance.name)
        slug = base_slug
        counter = 1
        while TodoCategory.objects.filter(
            organization=self.request.organization,
            slug=slug
        ).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        form.instance.slug = slug
        response = super().form_valid(form)
        messages.success(self.request, f'Category "{form.instance.name}" created.')
        return response

    def get_success_url(self):
        return reverse('todos:category_list')


class CategoryUpdateView(OrganizationViewMixin, UpdateView):
    """Update an existing todo category."""
    model = TodoCategory
    template_name = 'todos/category_form.html'
    fields = ['name', 'color', 'icon', 'order']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop('organization', None)  # Remove org kwarg - auto-generated form doesn't accept it
        return kwargs

    def get_queryset(self):
        return TodoCategory.objects.filter(organization=self.request.organization)

    def form_valid(self, form):
        # Update slug if name changed
        new_slug = slugify(form.instance.name)
        if new_slug != self.object.slug:
            base_slug = new_slug
            slug = base_slug
            counter = 1
            while TodoCategory.objects.filter(
                organization=self.request.organization,
                slug=slug
            ).exclude(pk=self.object.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            form.instance.slug = slug
        response = super().form_valid(form)
        messages.success(self.request, f'Category "{form.instance.name}" updated.')
        return response

    def get_success_url(self):
        return reverse('todos:category_list')


class CategoryDeleteView(OrganizationViewMixin, DeleteView):
    """Delete a todo category."""
    model = TodoCategory
    template_name = 'todos/category_confirm_delete.html'

    def get_queryset(self):
        return TodoCategory.objects.filter(organization=self.request.organization)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['todo_count'] = Todo.objects.filter(
            category=self.object,
            is_deleted=False
        ).count()
        return context

    def form_valid(self, form):
        category = self.object

        # Prevent deletion of system categories
        if category.is_system:
            messages.error(self.request, 'System categories cannot be deleted.')
            return redirect('todos:category_list')

        # Check if category has todos
        todo_count = Todo.objects.filter(category=category, is_deleted=False).count()
        if todo_count > 0:
            messages.error(
                self.request,
                f'Cannot delete category "{category.name}" - it has {todo_count} todo(s). '
                'Please reassign or delete the todos first.'
            )
            return redirect('todos:category_list')

        name = category.name
        response = super().form_valid(form)
        messages.success(self.request, f'Category "{name}" deleted.')
        return response

    def get_success_url(self):
        return reverse('todos:category_list')
